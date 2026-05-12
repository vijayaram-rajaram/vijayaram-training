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
