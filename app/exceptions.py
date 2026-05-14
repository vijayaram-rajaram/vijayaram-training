"""
app/exceptions.py
-----------------
Domain-specific exception hierarchy for the Customer CRUD API.

These exceptions are raised exclusively by the **service layer** and
translated into appropriate HTTP error responses by the **route layer**.
Keeping exceptions in their own module avoids circular imports and makes
the error contract between layers explicit.

Classes
-------
CustomerNotFoundError
    Raised when a requested customer ID does not exist in the database.
EmailAlreadyExistsError
    Raised when a new or updated email is already registered to another
    customer.
ValidationError
    Raised when required fields are missing or have invalid values.
"""


class CustomerNotFoundError(Exception):
    """Customer with the given ID does not exist in the database.

    Attributes:
        customer_id (int): The ID that was searched for.
    """

    def __init__(self, customer_id: int) -> None:
        super().__init__(f"Customer {customer_id} not found.")
        self.customer_id = customer_id


class EmailAlreadyExistsError(Exception):
    """Email address is already registered to another customer.

    Attributes:
        email (str): The duplicate email that triggered the error.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"Email '{email}' is already registered.")
        self.email = email


class ValidationError(Exception):
    """Input data failed domain validation.

    Raised when required fields are absent, blank, or otherwise invalid
    before any database operation is attempted.
    """


# ---------------------------------------------------------------------------
# Third-party / integration exceptions
# ---------------------------------------------------------------------------


class ExternalAPIError(Exception):
    """A third-party API call failed for a non-retriable reason.

    Attributes:
        status_code (int | None): HTTP status returned by the remote API,
            or ``None`` when no response was received (e.g. network error).
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ExternalAPITimeoutError(ExternalAPIError):
    """The remote API did not respond within the configured timeout."""

    def __init__(self, url: str) -> None:
        # Avoid logging the full URL (may contain tokens in query params).
        super().__init__(f"Request timed out while calling external API at {url!r}.")


class ExternalAPIRateLimitError(ExternalAPIError):
    """The remote API returned HTTP 429 (Too Many Requests).

    Attributes:
        retry_after (int | None): Seconds to wait before retrying, when
            the ``Retry-After`` header was present in the response.
    """

    def __init__(self, retry_after: int | None = None) -> None:
        msg = "External API rate limit exceeded."
        if retry_after is not None:
            msg += f" Retry after {retry_after}s."
        super().__init__(msg, status_code=429)
        self.retry_after = retry_after


class ExternalAPIUnavailableError(ExternalAPIError):
    """The remote API is temporarily unavailable (5xx response)."""

    def __init__(self, status_code: int) -> None:
        super().__init__(
            f"External API returned {status_code} – service unavailable.",
            status_code=status_code,
        )
