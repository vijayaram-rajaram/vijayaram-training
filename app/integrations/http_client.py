"""
app/integrations/http_client.py
--------------------------------
Reusable, secure HTTP client base class for third-party API integrations.

Security practices implemented
-------------------------------
* **API key management** – keys are injected via the ``Authorization``
  header (Bearer scheme) and sourced exclusively from constructor
  arguments (which are read from environment variables by callers).
  Keys are *never* logged or included in exception messages.
* **Secrets scrubbing** – the ``_safe_url`` helper strips query-string
  tokens before they appear in logs or exception text.
* **Timeout enforcement** – every request has a hard deadline so the
  calling thread cannot hang indefinitely.
* **Retry with exponential back-off** – transient errors (5xx, network
  hiccups, timeouts) are retried up to *max_retries* times using
  ``tenacity``.  HTTP 429 (rate-limit) is treated as a hard stop rather
  than a retry trigger to avoid amplifying load on the remote server.

Usage::

    class MyClient(BaseHTTPClient):
        def __init__(self):
            super().__init__(
                base_url="https://api.example.com",
                api_key=os.environ.get("MY_API_KEY"),
                timeout=10,
                max_retries=3,
                backoff=0.5,
            )

        def get_item(self, item_id: int) -> dict:
            return self.get(f"/items/{item_id}")
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.util.retry import Retry

from app.exceptions import (
    ExternalAPIError,
    ExternalAPIRateLimitError,
    ExternalAPITimeoutError,
    ExternalAPIUnavailableError,
)

logger = logging.getLogger(__name__)

# Regex that matches common query-string patterns containing secrets.
_SECRET_PARAMS_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|apikey|access[_-]?token)=[^&]*",
    re.IGNORECASE,
)


def _safe_url(url: str) -> str:
    """Return *url* with any secret query parameters redacted.

    Args:
        url (str): Raw URL that may contain sensitive query parameters.

    Returns:
        str: URL with secret values replaced by ``[REDACTED]``.
    """
    return _SECRET_PARAMS_RE.sub(r"\1=[REDACTED]", url)


class BaseHTTPClient:
    """Reusable HTTP client with retry, timeout, and API-key support.

    Sub-class this to build concrete third-party API clients.  Overriding
    ``_get_headers`` lets you customise how credentials are transmitted
    (e.g. ``X-API-Key`` header instead of ``Authorization: Bearer``).

    Args:
        base_url (str): Root URL of the target API (trailing slash stripped).
        api_key (str | None): Optional Bearer token.  ``None`` or empty
            string means no ``Authorization`` header is sent.
        timeout (int): Per-request timeout in seconds.  Defaults to 10.
        max_retries (int): Total retry attempts for transient failures.
            Set to 0 to disable retries entirely (useful in tests).
        backoff (float): Multiplier for exponential back-off in seconds.
            Actual wait = backoff × 2^(attempt − 1).  Defaults to 0.5.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 10,
        max_retries: int = 3,
        backoff: float = 0.5,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Store the key in a private slot; never expose via __repr__ or logs.
        self.__api_key: str | None = api_key if api_key else None
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff
        self._session = self._build_session()

    # ------------------------------------------------------------------
    # Session / connection setup
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """Build a ``requests.Session`` with transport-level retry logic.

        urllib3 ``Retry`` handles connection/read failures and idempotent
        request retries at the transport layer.  Application-level retry
        (e.g. for HTTP 500 responses that DO return a body) is handled by
        ``tenacity`` in ``_request``.

        Returns:
            requests.Session: Configured session instance.
        """
        session = requests.Session()

        # Only retry truly idempotent methods at the transport layer.
        # Application-level retry via tenacity covers the rest.
        retry_strategy = Retry(
            total=self._max_retries,
            backoff_factor=self._backoff,
            # Retry on these status codes at the transport adapter level.
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "OPTIONS"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # ------------------------------------------------------------------
    # Header construction
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build the default request headers.

        Subclasses may override this method to change authentication
        scheme (e.g. ``X-API-Key`` header) without touching the rest of
        the client.

        Returns:
            dict[str, str]: Headers to attach to every outbound request.
        """
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.__api_key:
            headers["Authorization"] = f"Bearer {self.__api_key}"
        return headers

    # ------------------------------------------------------------------
    # Core request method (with tenacity retry)
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Execute an HTTP request and return the parsed JSON body.

        Retries on ``ExternalAPIUnavailableError`` using exponential
        back-off.  ``ExternalAPIRateLimitError`` and
        ``ExternalAPITimeoutError`` are *not* retried – they propagate
        immediately to the caller.

        Args:
            method (str): HTTP verb (``"GET"``, ``"POST"``, …).
            path (str): Path relative to ``base_url`` (leading slash
                optional).
            params (dict | None): Query-string parameters.
            json: Request body to serialise as JSON.

        Returns:
            Any: Parsed JSON response (dict or list).

        Raises:
            ExternalAPITimeoutError: Request exceeded ``self._timeout``.
            ExternalAPIRateLimitError: Remote returned HTTP 429.
            ExternalAPIUnavailableError: Remote returned a 5xx status.
            ExternalAPIError: Any other HTTP or connection error.
        """
        url = f"{self._base_url}/{path.lstrip('/')}"

        @retry(
            retry=retry_if_exception_type(ExternalAPIUnavailableError),
            stop=stop_after_attempt(max(1, self._max_retries)),
            wait=wait_exponential(multiplier=self._backoff, min=self._backoff, max=30),
            reraise=True,
        )
        def _do_request() -> Any:
            try:
                logger.debug("Outbound %s %s", method, _safe_url(url))
                response = self._session.request(
                    method,
                    url,
                    headers=self._get_headers(),
                    params=params,
                    json=json,
                    timeout=self._timeout,
                )
            except requests.Timeout:
                logger.warning("Timeout calling %s", _safe_url(url))
                raise ExternalAPITimeoutError(_safe_url(url))
            except requests.ConnectionError as exc:
                logger.warning("Connection error calling %s: %s", _safe_url(url), exc)
                raise ExternalAPIError(
                    f"Could not connect to external API at {_safe_url(url)!r}."
                )

            # --- Rate-limit: do NOT retry to avoid amplifying server load ---
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    retry_after_int: int | None = int(retry_after) if retry_after else None
                except ValueError:
                    retry_after_int = None
                logger.warning("Rate-limited by external API (%s)", _safe_url(url))
                raise ExternalAPIRateLimitError(retry_after=retry_after_int)

            # --- 5xx: retriable via tenacity ----------------------------------
            if response.status_code >= 500:
                logger.warning(
                    "External API returned %s for %s",
                    response.status_code,
                    _safe_url(url),
                )
                raise ExternalAPIUnavailableError(response.status_code)

            # --- Other 4xx: hard failure --------------------------------------
            if response.status_code >= 400:
                logger.error(
                    "External API client error %s for %s",
                    response.status_code,
                    _safe_url(url),
                )
                raise ExternalAPIError(
                    f"External API returned {response.status_code}.",
                    status_code=response.status_code,
                )

            return response.json()

        try:
            return _do_request()
        except RetryError as exc:
            # Tenacity exhausted all attempts; unwrap the underlying cause.
            raise ExternalAPIUnavailableError(503) from exc

    # ------------------------------------------------------------------
    # Public HTTP helpers
    # ------------------------------------------------------------------

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform a GET request.

        Args:
            path (str): API path relative to ``base_url``.
            params (dict | None): Optional query-string parameters.

        Returns:
            Any: Parsed JSON response.
        """
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform a POST request.

        Args:
            path (str): API path relative to ``base_url``.
            json: Request body (will be JSON-serialised).
            params (dict | None): Optional query-string parameters.

        Returns:
            Any: Parsed JSON response.
        """
        return self._request("POST", path, params=params, json=json)
