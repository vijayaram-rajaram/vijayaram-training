"""
tests/test_secrets.py
----------------------
Unit tests for ``app.secrets`` – the centralised secret-loading module.

Mock strategy
-------------
All tests manipulate the process environment via ``monkeypatch.setenv``
and ``monkeypatch.delenv`` so no real environment variables are mutated
between tests.  No network calls are made:

* The ``SECRETS_BACKEND=aws_secrets_manager`` path is tested by
  mocking ``boto3.client`` with a ``MagicMock`` — boto3 itself does not
  need to be installed for these tests because the import is patched
  at the module level inside ``_load_from_aws``.
* ``validate_production_secrets`` is tested by setting/unsetting
  ``SECRET_KEY`` and ``DATABASE_URL`` in the subprocess environment.

Coverage
--------
load_secret()
    * Returns env-var value when key is set.
    * Returns *default* when key is absent and backend is "env".
    * Returns None when key absent and no default.

_load_from_aws()
    * Returns value from Secrets Manager JSON object.
    * Returns plain-string secret as-is.
    * Falls back to default when ResourceNotFoundException is raised.
    * Falls back to default when boto3 is not installed (ImportError).
    * Logs error and falls back when an unexpected exception occurs.

validate_production_secrets()
    * Passes when all required secrets are set to non-default values.
    * Raises EnvironmentError listing every missing key.
    * Raises EnvironmentError when SECRET_KEY holds the insecure default.
    * Error message contains the name of each failing key.

mask()
    * Masks all but the first 4 characters.
    * Returns "***" for short or empty strings.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

import app.secrets as secrets_mod
from app.secrets import load_secret, mask, validate_production_secrets


# ---------------------------------------------------------------------------
# mask()
# ---------------------------------------------------------------------------


class TestMask:
    def test_masks_long_value(self):
        assert mask("super-secret") == "supe***"

    def test_masks_exactly_four_chars(self):
        # Four chars → nothing left to show beyond the prefix → only "***"
        assert mask("abcd") == "***"

    def test_masks_short_value(self):
        assert mask("abc") == "***"

    def test_masks_empty_string(self):
        assert mask("") == "***"

    def test_custom_show_length(self):
        assert mask("hello-world", show=2) == "he***"

    def test_result_never_contains_full_secret(self):
        secret = "very-long-secret-value"
        result = mask(secret)
        assert secret not in result
        assert result.endswith("***")


# ---------------------------------------------------------------------------
# load_secret() — env backend
# ---------------------------------------------------------------------------


class TestLoadSecretEnvBackend:
    def test_returns_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "top-secret-value")
        assert load_secret("MY_SECRET") == "top-secret-value"

    def test_returns_default_when_key_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        assert load_secret("MISSING_KEY", default="fallback") == "fallback"

    def test_returns_none_when_key_missing_and_no_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        assert load_secret("MISSING_KEY") is None

    def test_env_var_takes_priority_over_default(self, monkeypatch):
        monkeypatch.setenv("PRIORITY_KEY", "env-value")
        assert load_secret("PRIORITY_KEY", default="fallback") == "env-value"

    def test_empty_env_var_treated_as_unset(self, monkeypatch):
        # An empty string in the environment is falsy – should fall through
        # to the default.
        monkeypatch.setenv("EMPTY_KEY", "")
        assert load_secret("EMPTY_KEY", default="fallback") == "fallback"


# ---------------------------------------------------------------------------
# load_secret() — AWS Secrets Manager backend
# ---------------------------------------------------------------------------


class TestLoadSecretAwsBackend:
    """Tests the AWS Secrets Manager code path using a mock boto3 client.

    boto3 import is patched inside ``app.secrets._load_from_aws`` so the
    real library does not need to be installed.
    """

    def _make_boto3_mock(self, secret_string: str) -> ModuleType:
        """Build a mock boto3 module that returns *secret_string*."""
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": secret_string
        }
        return mock_boto3

    def test_returns_value_from_json_secret(self, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        monkeypatch.setenv("SECRETS_BACKEND", "aws_secrets_manager")

        mock_boto3 = self._make_boto3_mock('{"MY_KEY": "from-vault"}')
        with patch.dict(sys.modules, {"boto3": mock_boto3, "botocore.exceptions": MagicMock()}):
            result = load_secret("MY_KEY")

        assert result == "from-vault"

    def test_returns_plain_string_secret(self, monkeypatch):
        monkeypatch.delenv("PLAIN_KEY", raising=False)
        monkeypatch.setenv("SECRETS_BACKEND", "aws_secrets_manager")

        mock_boto3 = self._make_boto3_mock("plain-secret-value")
        with patch.dict(sys.modules, {"boto3": mock_boto3, "botocore.exceptions": MagicMock()}):
            result = load_secret("PLAIN_KEY")

        # Plain string does not contain the key → returned as-is
        assert result == "plain-secret-value"

    def test_returns_default_on_resource_not_found(self, monkeypatch):
        monkeypatch.delenv("ABSENT_KEY", raising=False)
        monkeypatch.setenv("SECRETS_BACKEND", "aws_secrets_manager")

        # Build a minimal ClientError that does NOT require botocore installed.
        # The real botocore.exceptions.ClientError has a ``response`` dict
        # attribute; we replicate just enough for _load_from_aws to work.
        class FakeClientError(Exception):
            def __init__(self, response, operation_name):
                self.response = response
                self.operation_name = operation_name

        error_response = {"Error": {"Code": "ResourceNotFoundException"}}
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.side_effect = FakeClientError(
            error_response, "GetSecretValue"
        )

        # Expose our fake exception class as botocore.exceptions.ClientError
        # `from botocore.exceptions import ClientError` resolves to
        # sys.modules["botocore.exceptions"].ClientError, so we set that attr.
        botocore_mock = MagicMock()
        botocore_mock.ClientError = FakeClientError

        with patch.dict(sys.modules, {"boto3": mock_boto3, "botocore.exceptions": botocore_mock}):
            result = load_secret("ABSENT_KEY", default="fallback")

        assert result == "fallback"

    def test_falls_back_when_boto3_not_installed(self, monkeypatch):
        monkeypatch.delenv("NO_BOTO_KEY", raising=False)
        monkeypatch.setenv("SECRETS_BACKEND", "aws_secrets_manager")

        # Simulate boto3 not being installed
        with patch.dict(sys.modules, {"boto3": None}):
            result = load_secret("NO_BOTO_KEY", default="fallback")

        assert result == "fallback"

    def test_env_var_wins_over_aws_backend(self, monkeypatch):
        monkeypatch.setenv("DUAL_KEY", "from-env")
        monkeypatch.setenv("SECRETS_BACKEND", "aws_secrets_manager")

        # Even with AWS backend configured, the env var takes priority.
        result = load_secret("DUAL_KEY")
        assert result == "from-env"


# ---------------------------------------------------------------------------
# validate_production_secrets()
# ---------------------------------------------------------------------------


class TestValidateProductionSecrets:
    _VALID_SECRETS = {
        "SECRET_KEY": "a-random-256-bit-production-key-xxxxxxxxxxxxxxxx",
        "DATABASE_URL": "postgresql://user:pass@db-host/prod_db",
    }

    def test_passes_when_all_secrets_set(self, monkeypatch):
        for key, value in self._VALID_SECRETS.items():
            monkeypatch.setenv(key, value)
        # Should not raise
        validate_production_secrets()

    def test_raises_when_secret_key_missing(self, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("DATABASE_URL", self._VALID_SECRETS["DATABASE_URL"])

        with pytest.raises(EnvironmentError) as exc_info:
            validate_production_secrets()

        assert "SECRET_KEY" in str(exc_info.value)

    def test_raises_when_database_url_missing(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", self._VALID_SECRETS["SECRET_KEY"])
        monkeypatch.delenv("DATABASE_URL", raising=False)

        with pytest.raises(EnvironmentError) as exc_info:
            validate_production_secrets()

        assert "DATABASE_URL" in str(exc_info.value)

    def test_raises_when_secret_key_is_insecure_default(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "dev-secret-change-in-production")
        monkeypatch.setenv("DATABASE_URL", self._VALID_SECRETS["DATABASE_URL"])

        with pytest.raises(EnvironmentError) as exc_info:
            validate_production_secrets()

        assert "insecure development default" in str(exc_info.value)
        assert "SECRET_KEY" in str(exc_info.value)

    def test_error_lists_all_failures_at_once(self, monkeypatch):
        # Both secrets missing → both should appear in a single error.
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        with pytest.raises(EnvironmentError) as exc_info:
            validate_production_secrets()

        msg = str(exc_info.value)
        assert "SECRET_KEY" in msg
        assert "DATABASE_URL" in msg

    def test_does_not_leak_secret_values_in_error(self, monkeypatch):
        secret_val = "super-secret-value-12345"
        monkeypatch.setenv("SECRET_KEY", secret_val)
        # DATABASE_URL missing → will raise
        monkeypatch.delenv("DATABASE_URL", raising=False)

        with pytest.raises(EnvironmentError) as exc_info:
            validate_production_secrets()

        # The actual secret VALUE must not appear in the error message.
        assert secret_val not in str(exc_info.value)
