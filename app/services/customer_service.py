"""
app/services/customer_service.py
---------------------------------
Business logic layer for customer CRUD operations.

All persistence is delegated to the in-memory store in ``app.data.mock_data``.
The service layer is intentionally decoupled from Flask so it can be tested
independently of the HTTP layer.

Classes
-------
CustomerService
    Provides create / read / update / delete methods for Customer records.
"""

from typing import Any

from app.data.mock_data import get_next_id, get_store
from app.models.customer import Customer

# Fields required when creating a new customer
_REQUIRED_FIELDS: frozenset[str] = frozenset({"name", "email", "phone", "address"})


class CustomerService:
    """Encapsulates all business logic for customer management.

    The service operates on the shared in-memory store and enforces
    domain rules such as email uniqueness and required-field validation.
    """

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        """Return every customer in the store.

        Returns:
            list[dict]: Serialized list of all customer records.
        """
        return [c.to_dict() for c in get_store().values()]

    def get_by_id(self, customer_id: int) -> dict | None:
        """Return a single customer by primary key.

        Args:
            customer_id (int): The unique customer ID to look up.

        Returns:
            dict | None: Serialized customer, or ``None`` if not found.
        """
        customer = get_store().get(customer_id)
        return customer.to_dict() if customer else None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create(self, data: dict[str, Any]) -> dict:
        """Add a new customer to the store.

        Args:
            data (dict): Must contain ``name``, ``email``, ``phone``, and
                ``address`` keys.

        Returns:
            dict: The newly created customer record.

        Raises:
            ValueError: If required fields are missing or the email is
                already registered.
        """
        self._validate_required_fields(data)
        self._assert_email_unique(data["email"])

        new_id = get_next_id()
        customer = Customer(
            id=new_id,
            name=data["name"].strip(),
            email=data["email"].strip().lower(),
            phone=data["phone"].strip(),
            address=data["address"].strip(),
        )
        get_store()[new_id] = customer
        return customer.to_dict()

    def update(self, customer_id: int, data: dict[str, Any]) -> dict | None:
        """Partially update an existing customer.

        Only keys present in *data* are modified; all others are left
        unchanged (PATCH semantics applied via the PUT endpoint).

        Args:
            customer_id (int): ID of the customer to update.
            data (dict): Fields to update (any subset of name / email /
                phone / address).

        Returns:
            dict | None: Updated customer, or ``None`` if ID not found.

        Raises:
            ValueError: If the supplied email is already taken by a
                different customer.
        """
        store = get_store()
        customer = store.get(customer_id)
        if customer is None:
            return None

        if "email" in data:
            self._assert_email_unique(data["email"].strip().lower(), exclude_id=customer_id)
            customer.email = data["email"].strip().lower()

        if "name" in data:
            customer.name = data["name"].strip()
        if "phone" in data:
            customer.phone = data["phone"].strip()
        if "address" in data:
            customer.address = data["address"].strip()

        return customer.to_dict()

    def delete(self, customer_id: int) -> bool:
        """Remove a customer from the store.

        Args:
            customer_id (int): ID of the customer to delete.

        Returns:
            bool: ``True`` if the record was deleted, ``False`` if the
                ID did not exist.
        """
        store = get_store()
        if customer_id not in store:
            return False
        del store[customer_id]
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_required_fields(data: dict[str, Any]) -> None:
        """Raise ``ValueError`` if any required field is absent.

        Args:
            data (dict): The incoming request payload.

        Raises:
            ValueError: Lists all missing fields in the message.
        """
        missing = _REQUIRED_FIELDS - data.keys()
        if missing:
            raise ValueError(f"Missing required fields: {sorted(missing)}")

    @staticmethod
    def _assert_email_unique(email: str, exclude_id: int | None = None) -> None:
        """Raise ``ValueError`` if the email is already in use.

        Args:
            email (str): Email address to check.
            exclude_id (int | None): Customer ID to skip during the
                check (used for update to allow keeping the same email).

        Raises:
            ValueError: If the email belongs to another customer record.
        """
        normalised = email.strip().lower()
        for customer in get_store().values():
            if customer.email == normalised and customer.id != exclude_id:
                raise ValueError(f"Email '{normalised}' is already registered.")
