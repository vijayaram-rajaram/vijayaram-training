"""
tests/test_http_client.py
--------------------------
Unit tests for ``app.integrations.http_client.BaseHTTPClient``.

Mock strategy
-------------
All outbound HTTP calls are intercepted by the ``responses`` library
(https://github.com/getsentry/responses).  Decorating a test with
``@responses.activate`` (or ``@rsps_lib.activate`` as aliased here)
installs a transport-level shim that:

  1. Raises ``ConnectionError`` for any URL not explicitly registered.
  2. Returns the registered fake response for any URL that **is**
     registered — without opening a real socket.

This means tests run offline, are deterministic, and cannot accidentally
call a real third-party API during CI.

Registration syntax::

    rsps_lib.add(
        rsps_lib.GET,                        # HTTP method
        "https://test.example.com/users/1",  # URL to intercept
        json={"id": 1, "name": "Alice"},     # fake response body
        status=200,                          # fake HTTP status
    )

Real JSONPlaceholder response shape (for reference)::

    GET https://jsonplaceholder.typicode.com/users/1
    → 200 OK
    {
        "id": 1,
        "name": "Leanne Graham",
        "username": "Bret",
        "email": "Sincere@april.biz",
        "address": { "street": "Kulas Light", "city": "Gwenborough", ... },
        "phone": "1-770-736-8031 x56442",
        "website": "hildegard.org",
        "company": { "name": "Romaguera-Crona", ... }
    }

    GET https://jsonplaceholder.typicode.com/posts?userId=1
    → 200 OK
    [
        { "userId": 1, "id": 1, "title": "...", "body": "..." },
        ...
    ]

Coverage
--------
* Successful GET / POST requests return parsed JSON.
* Timeout → ``ExternalAPITimeoutError``.
* Connection error → ``ExternalAPIError``.
* HTTP 429 → ``ExternalAPIRateLimitError`` (with and without Retry-After).
* HTTP 5xx → ``ExternalAPIUnavailableError``.
* HTTP 4xx → ``ExternalAPIError`` with the correct status code.
* ``_safe_url`` strips secret query parameters from URLs.
* API key is injected into the ``Authorization`` header when provided.
* No ``Authorization`` header is sent when no key is configured.
"""

import pytest
import requests as req
import responses as rsps_lib
from responses import RequestsMock

from app.exceptions import (
    ExternalAPIError,
    ExternalAPIRateLimitError,
    ExternalAPITimeoutError,
    ExternalAPIUnavailableError,
)
from app.integrations.http_client import BaseHTTPClient, _safe_url

BASE = "https://test.example.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(api_key: str | None = None, max_retries: int = 0) -> BaseHTTPClient:
    """Create a minimal BaseHTTPClient for testing."""
    return BaseHTTPClient(
        base_url=BASE,
        api_key=api_key,
        timeout=2,
        max_retries=max_retries,
        backoff=0.01,
    )


# ---------------------------------------------------------------------------
# _safe_url
# ---------------------------------------------------------------------------


class TestSafeUrl:
    def test_redacts_api_key_param(self):
        url = "https://api.example.com/data?api_key=supersecret&page=1"
        safe = _safe_url(url)
        assert "supersecret" not in safe
        assert "page=1" in safe
        assert "[REDACTED]" in safe

    def test_redacts_token_param(self):
        url = "https://api.example.com/data?access_token=abc123"
        safe = _safe_url(url)
        assert "abc123" not in safe

    def test_clean_url_unchanged(self):
        url = "https://api.example.com/users?page=2&limit=10"
        assert _safe_url(url) == url


# ---------------------------------------------------------------------------
# Successful requests
# ---------------------------------------------------------------------------


class TestSuccessfulRequests:
    @rsps_lib.activate
    def test_get_returns_json_dict(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/users/1
        # Returns:     200 OK  {"id": 1, "name": "Alice"}
        # Mirrors:     GET https://jsonplaceholder.typicode.com/users/1
        #              → {"id": 1, "name": "Leanne Graham", "email": ...}
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/users/1", json={"id": 1, "name": "Alice"})
        client = _client()
        result = client.get("/users/1")
        assert result == {"id": 1, "name": "Alice"}

    @rsps_lib.activate
    def test_get_with_params(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/posts?userId=1
        # Returns:     200 OK  [{"id": 1}]
        # Mirrors:     GET https://jsonplaceholder.typicode.com/posts?userId=1
        #              → [{"userId": 1, "id": 1, "title": "...", "body": "..."}]
        # Also asserts the query-string is forwarded correctly.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/posts", json=[{"id": 1}])
        client = _client()
        result = client.get("/posts", params={"userId": 1})
        assert result == [{"id": 1}]
        assert "userId=1" in rsps_lib.calls[0].request.url

    @rsps_lib.activate
    def test_post_returns_json(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  POST https://test.example.com/items
        #              Body: {"name": "Widget"}
        # Returns:     201 Created  {"id": 99}
        # Verifies the POST helper serialises the body and parses the response.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.POST, f"{BASE}/items", json={"id": 99}, status=201)
        client = _client()
        result = client.post("/items", json={"name": "Widget"})
        assert result["id"] == 99

    @rsps_lib.activate
    def test_api_key_sent_as_bearer(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/secure
        # Returns:     200 OK  {"ok": True}
        # Asserts:     The outbound request carries
        #              Authorization: Bearer my-secret-key
        # This validates ENRICHMENT_API_KEY is forwarded correctly.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/secure", json={"ok": True})
        client = _client(api_key="my-secret-key")
        client.get("/secure")
        sent_auth = rsps_lib.calls[0].request.headers.get("Authorization", "")
        assert sent_auth == "Bearer my-secret-key"

    @rsps_lib.activate
    def test_no_auth_header_without_key(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/public
        # Returns:     200 OK  {}
        # Asserts:     No Authorization header is sent when ENRICHMENT_API_KEY
        #              is absent (public sandbox like JSONPlaceholder).
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/public", json={})
        client = _client(api_key=None)
        client.get("/public")
        assert "Authorization" not in rsps_lib.calls[0].request.headers


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    @rsps_lib.activate
    def test_timeout_raises_external_api_timeout_error(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/slow
        # Raises:      requests.exceptions.Timeout (transport-level)
        # Simulates:   Provider exceeds ENRICHMENT_API_TIMEOUT seconds.
        # Expected:    ExternalAPITimeoutError is raised (never retried).
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/slow", body=req.exceptions.Timeout())
        client = _client()
        with pytest.raises(ExternalAPITimeoutError):
            client.get("/slow")


# ---------------------------------------------------------------------------
# Connection error
# ---------------------------------------------------------------------------


class TestConnectionError:
    @rsps_lib.activate
    def test_connection_error_raises_external_api_error(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/broken
        # Raises:      requests.exceptions.ConnectionError (transport-level)
        # Simulates:   DNS failure, refused connection, or network partition.
        # Expected:    ExternalAPIError is raised with a safe (scrubbed) message.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(
            rsps_lib.GET, f"{BASE}/broken", body=req.exceptions.ConnectionError()
        )
        client = _client()
        with pytest.raises(ExternalAPIError):
            client.get("/broken")


# ---------------------------------------------------------------------------
# Rate limit (HTTP 429)
# ---------------------------------------------------------------------------


class TestRateLimit:
    @rsps_lib.activate
    def test_429_raises_rate_limit_error(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/limited
        # Returns:     429 Too Many Requests  (no body, no Retry-After)
        # Simulates:   Provider rate-limits this server.
        # Expected:    ExternalAPIRateLimitError raised immediately.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/limited", status=429)
        client = _client()
        with pytest.raises(ExternalAPIRateLimitError):
            client.get("/limited")

    @rsps_lib.activate
    def test_429_with_retry_after_header(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/limited
        # Returns:     429 Too Many Requests
        #              Headers: Retry-After: 30
        # Simulates:   Provider tells us to back off for 30 seconds.
        # Expected:    ExternalAPIRateLimitError with retry_after == 30.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(
            rsps_lib.GET,
            f"{BASE}/limited",
            status=429,
            headers={"Retry-After": "30"},
        )
        client = _client()
        with pytest.raises(ExternalAPIRateLimitError) as exc_info:
            client.get("/limited")
        assert exc_info.value.retry_after == 30

    @rsps_lib.activate
    def test_429_not_retried(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Registers TWO responses: first 429, then 200.
        # Verifies that retrying a rate-limit response is deliberately blocked
        # — retrying would amplify the load on the rate-limited server.
        # Expected:    Only 1 outbound call; ExternalAPIRateLimitError raised.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/limited", status=429)
        rsps_lib.add(rsps_lib.GET, f"{BASE}/limited", status=200, json={})
        client = _client(max_retries=3)
        with pytest.raises(ExternalAPIRateLimitError):
            client.get("/limited")
        # Only one call should have been made
        assert len(rsps_lib.calls) == 1


# ---------------------------------------------------------------------------
# 5xx errors
# ---------------------------------------------------------------------------


class TestServerErrors:
    @rsps_lib.activate
    def test_500_raises_unavailable_error(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/broken
        # Returns:     500 Internal Server Error
        # Simulates:   Provider crashes (unhandled exception on their side).
        # max_retries=0 so we see the error after a single attempt.
        # Expected:    ExternalAPIUnavailableError with status_code == 500.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/broken", status=500)
        client = _client(max_retries=0)
        with pytest.raises(ExternalAPIUnavailableError) as exc_info:
            client.get("/broken")
        assert exc_info.value.status_code == 500

    @rsps_lib.activate
    def test_503_raises_unavailable_error(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/broken
        # Returns:     503 Service Unavailable
        # Simulates:   Provider is down for maintenance or overloaded.
        # Expected:    ExternalAPIUnavailableError raised after retries exhausted.
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/broken", status=503)
        client = _client(max_retries=0)
        with pytest.raises(ExternalAPIUnavailableError):
            client.get("/broken")


# ---------------------------------------------------------------------------
# 4xx errors (non-429)
# ---------------------------------------------------------------------------


class TestClientErrors:
    @rsps_lib.activate
    def test_404_raises_external_api_error_with_status(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/missing
        # Returns:     404 Not Found
        # Simulates:   Requesting a user/resource that doesn't exist at the
        #              provider (e.g. GET /users/9999 on JSONPlaceholder).
        # Expected:    ExternalAPIError with status_code == 404 (not retried).
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/missing", status=404)
        client = _client()
        with pytest.raises(ExternalAPIError) as exc_info:
            client.get("/missing")
        assert exc_info.value.status_code == 404

    @rsps_lib.activate
    def test_401_raises_external_api_error(self):
        # ── Mock ─────────────────────────────────────────────────────────────
        # Intercepts:  GET https://test.example.com/auth
        # Returns:     401 Unauthorized
        # Simulates:   ENRICHMENT_API_KEY is invalid or expired.
        # Expected:    ExternalAPIError with status_code == 401 (not retried).
        # ─────────────────────────────────────────────────────────────────────
        rsps_lib.add(rsps_lib.GET, f"{BASE}/auth", status=401)
        client = _client()
        with pytest.raises(ExternalAPIError) as exc_info:
            client.get("/auth")
        assert exc_info.value.status_code == 401
