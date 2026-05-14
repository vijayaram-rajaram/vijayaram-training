"""
app/secrets.py
--------------
Centralised secret-loading with pluggable vault backends.

The module provides a single ``load_secret(key)`` entry-point that loads
secrets from a chain of backends in the following order:

1. **Environment variable** named *key* — always checked first, so any
   value injected by the shell, Docker, or a CI pipeline takes priority.
2. **AWS Secrets Manager** — activated when the ``SECRETS_BACKEND``
   environment variable is set to ``"aws_secrets_manager"``.  Requires
   ``boto3`` to be installed.  Uses the ``SECRETS_NAME_PREFIX`` env var
   as the secret namespace (default: ``"app"``).
3. *default* — returned when all backends are exhausted.

The ``validate_production_secrets`` function is called by the app
factory when starting in production mode.  It checks that every
required secret is present and not left at an insecure development
default, aborting startup with a clear error if validation fails.

Security practices
------------------
* Secret **values are never logged**.  Only the key name (a non-secret
  identifier) may appear in log messages.
* The ``mask()`` helper renders a safe, redacted representation of a
  secret value for health-check or diagnostic output.
* The module has no side-effects at import time; nothing is fetched
  until ``load_secret`` is explicitly called.

Extending to other vault providers
-----------------------------------
Add a new ``_load_from_<provider>(key, default)`` function following the
same signature as ``_load_from_aws``, then insert a branch in
``load_secret`` keyed on a new ``SECRETS_BACKEND`` value:

    elif backend == "hashicorp_vault":
        return _load_from_hashicorp_vault(key, default)

Usage::

    from app.secrets import load_secret, validate_production_secrets

    api_key = load_secret("ENRICHMENT_API_KEY")            # → str | None
    db_url  = load_secret("DATABASE_URL", default="...")   # → str

    validate_production_secrets()   # raises EnvironmentError on failure
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required secrets that must be configured before production startup
# ---------------------------------------------------------------------------

#: Keys that must be present (non-empty) in production.
_REQUIRED_PRODUCTION_SECRETS: tuple[str, ...] = (
    "SECRET_KEY",
    "DATABASE_URL",
)

#: Key → value pairs that are known insecure development defaults.
#: Startup is aborted if any of these are detected in production.
_INSECURE_DEFAULTS: dict[str, str] = {
    "SECRET_KEY": "dev-secret-change-in-production",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def mask(value: str, show: int = 4) -> str:
    """Return a safely masked representation of *value* for display.

    Only the first *show* characters are kept; the remainder is replaced
    with ``***``.  Useful for health-check endpoints or diagnostic logs
    where you want to confirm a secret is *set* without revealing it.

    Args:
        value (str): The secret value to mask.
        show (int): Number of leading characters to keep.  Defaults to 4.

    Returns:
        str: Masked string, e.g. ``"sk-t***"`` for ``"sk-top_secret"``.

    Examples::

        mask("super-secret-key")   # → "supe***"
        mask("x")                  # → "***"       (too short to show any)
        mask("")                   # → "***"
    """
    if not value or len(value) <= show:
        return "***"
    return value[:show] + "***"


def load_secret(key: str, default: str | None = None) -> str | None:
    """Load a secret by name from the configured backend.

    Lookup order:
        1. Environment variable named *key*.
        2. AWS Secrets Manager (when ``SECRETS_BACKEND=aws_secrets_manager``).
        3. *default*.

    The environment-variable check always runs first so that values set
    by the shell, Docker ``-e``, or a CI pipeline override anything in a
    remote vault.

    Args:
        key (str): Secret name.  Must match the environment variable name
            and the key used inside the vault secret.
        default (str | None): Value to return when no backend provides
            the secret.  Defaults to ``None``.

    Returns:
        str | None: The secret value, or *default* when not found.
    """
    # 1. Environment variable — cheapest check, always first.
    env_value = os.environ.get(key)
    if env_value:
        return env_value

    # 2. Remote vault backend.
    backend = os.environ.get("SECRETS_BACKEND", "env").lower()
    if backend == "aws_secrets_manager":
        return _load_from_aws(key, default)

    # 3. Fall back to the provided default.
    return default


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------


def _load_from_aws(key: str, default: str | None = None) -> str | None:
    """Load a secret from AWS Secrets Manager.

    The secret is looked up by the name ``<SECRETS_NAME_PREFIX>/<key>``
    (prefix defaults to ``"app"`` when ``SECRETS_NAME_PREFIX`` is unset).

    AWS Secrets Manager stores secrets as either:
    * A **JSON object** — ``load_secret`` returns the value for the
      matching key inside the object.
    * A **plain string** — returned as-is.

    Credentials are resolved by ``boto3`` using the standard chain:
    IAM instance role → ``~/.aws/credentials`` →
    ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` env vars.

    Args:
        key (str): Secret key name.
        default (str | None): Fallback when the secret is absent, boto3
            is not installed, or the AWS call fails.

    Returns:
        str | None: Secret value or *default*.

    Note:
        Errors are logged at WARNING/ERROR level but never re-raised so
        the application can still start (possibly in degraded mode) rather
        than crashing on a transient AWS API hiccup.
    """
    try:
        import json as _json  # noqa: PLC0415

        import boto3  # noqa: PLC0415
        from botocore.exceptions import ClientError  # noqa: PLC0415
    except ImportError:
        logger.warning(
            "SECRETS_BACKEND=aws_secrets_manager is set but boto3 is not "
            "installed.  Falling back to environment variable for %r.  "
            "Install boto3 with: pip install boto3",
            key,
        )
        return default

    prefix = os.environ.get("SECRETS_NAME_PREFIX", "app")
    secret_name = f"{prefix}/{key}"
    region = os.environ.get("AWS_REGION", "us-east-1")

    try:
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secret_string: str = response.get("SecretString", "")

        # Secrets Manager can store the value as a JSON object or a bare string.
        try:
            data: dict[str, Any] = _json.loads(secret_string)
            return data.get(key, default)
        except (ValueError, TypeError):
            return secret_string or default

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            logger.warning(
                "Secret %r not found in AWS Secrets Manager (prefix=%r).",
                key,
                prefix,
            )
        else:
            # Log the error code only — never log the response body which may
            # contain partial secret material.
            logger.error(
                "AWS Secrets Manager error for %r: %s",
                key,
                error_code,
            )
        return default
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Unexpected error loading %r from AWS Secrets Manager: %s",
            key,
            type(exc).__name__,
        )
        return default


# ---------------------------------------------------------------------------
# Production startup validation
# ---------------------------------------------------------------------------


def validate_production_secrets() -> None:
    """Verify all required production secrets are properly configured.

    Called by the Flask app factory when ``FLASK_ENV=production``.
    Raises immediately so mis-configuration is surfaced at container
    start time rather than silently at request time.

    Checks:
        1. Every key in ``_REQUIRED_PRODUCTION_SECRETS`` resolves to a
           non-empty value via ``load_secret``.
        2. No key retains a known insecure development default value.

    Raises:
        EnvironmentError: If any required secret is missing or holds an
            insecure default.  The error message lists every violation so
            operators can fix all problems in one pass.

    Example error::

        EnvironmentError: Production startup aborted – secret errors:
          - 'SECRET_KEY' is still the insecure development default.
          - 'DATABASE_URL' is not set.
        Set these via environment variables or set SECRETS_BACKEND.
    """
    errors: list[str] = []

    for key in _REQUIRED_PRODUCTION_SECRETS:
        value = load_secret(key)

        if not value:
            errors.append(f"  - {key!r} is not set.")
            continue

        insecure_default = _INSECURE_DEFAULTS.get(key)
        if insecure_default and value == insecure_default:
            errors.append(
                f"  - {key!r} is still the insecure development default."
            )

    if errors:
        raise EnvironmentError(
            "Production startup aborted – secret errors:\n"
            + "\n".join(errors)
            + "\nSet these via environment variables or set SECRETS_BACKEND."
        )

    logger.info("Production secret validation passed.")
