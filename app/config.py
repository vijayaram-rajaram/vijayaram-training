"""
app/config.py
-------------
Application configuration classes.

Three environments are provided:

* ``DevelopmentConfig`` – SQLite file-based database, debug mode on.
* ``TestingConfig``     – SQLite **in-memory** database for isolated test runs.
* ``ProductionConfig``  – database URL read from the ``DATABASE_URL``
  environment variable.

Usage::

    from app.config import config
    app.config.from_object(config["testing"])
"""

import os


class _BaseConfig:
    """Shared defaults applied across all environments."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

    # ------------------------------------------------------------------
    # Third-party integration settings
    # All sensitive values (API keys, tokens) are read exclusively from
    # environment variables – never hardcoded.
    # ------------------------------------------------------------------

    #: Base URL for the customer-enrichment API.
    ENRICHMENT_API_BASE_URL: str = os.environ.get(
        "ENRICHMENT_API_BASE_URL", "https://jsonplaceholder.typicode.com"
    )

    #: Optional Bearer token / API key for the enrichment API.
    #: Leave unset (or blank) for APIs that do not require authentication
    #: (e.g. the public JSONPlaceholder sandbox).
    ENRICHMENT_API_KEY: str | None = os.environ.get("ENRICHMENT_API_KEY") or None

    #: Per-request timeout in seconds for outbound HTTP calls.
    ENRICHMENT_API_TIMEOUT: int = int(os.environ.get("ENRICHMENT_API_TIMEOUT", "10"))

    #: Maximum number of retry attempts on transient failures (5xx / network).
    ENRICHMENT_API_MAX_RETRIES: int = int(os.environ.get("ENRICHMENT_API_MAX_RETRIES", "3"))

    #: Multiplier (seconds) for exponential back-off between retries.
    ENRICHMENT_API_BACKOFF: float = float(os.environ.get("ENRICHMENT_API_BACKOFF", "0.5"))


class DevelopmentConfig(_BaseConfig):
    """Local development: SQLite file on disk, debug output enabled."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", "sqlite:///customers_dev.db"
    )


class TestingConfig(_BaseConfig):
    """Test suite: in-memory SQLite, completely isolated per test run."""

    TESTING = True
    DEBUG = False
    # Each test receives a brand-new in-memory database – no shared state.
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"

    # Use very short timeouts and disable real retries so tests are fast
    # and do not make real outbound HTTP calls.
    ENRICHMENT_API_TIMEOUT: int = 2
    ENRICHMENT_API_MAX_RETRIES: int = 0


class ProductionConfig(_BaseConfig):
    """Production: requires ``DATABASE_URL`` to be set in the environment."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI: str = os.environ.get("DATABASE_URL", "sqlite:///customers.db")


#: Mapping of environment name → config class used by the app factory.
config: dict[str, type[_BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
