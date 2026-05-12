"""
app/services/customer_service.py
---------------------------------
Business-logic layer for customer CRUD operations.

``CustomerService`` enforces domain rules (required fields, email
uniqueness) and delegates all persistence to ``CustomerRepository``.
It is intentionally decoupled from Flask so it can be unit-tested
without starting a server or touching a real database – callers may
inject a mock repository for fully isolated tests.

Classes
-------
CustomerService
    Create / read / update / delete operations for Customer records.
"""

from typing import Any

from app.exceptions import CustomerNotFoundError, EmailAlreadyExistsError, ValidationError
from app.models.customer import Customer
from app.repositories.customer_repo import CustomerRepository

#: Fields that must be present and non-blank when creating a new customer.
_REQUIRED_FIELDS: frozenset[str] = frozenset({"name", "email", "phone", "address"})


class CustomerService:
    """Business logic for customer management.

    Dependency injection is used for the repository so the service can
    be tested in isolation::

        mock_repo = MagicMock(spec=CustomerRepository)
        service   = CustomerService(repository=mock_repo)

    Args:
        repository (CustomerRepository | None): Data-access object.
            Defaults to a real ``CustomerRepository`` instance when
            ``None`` is passed (production path).
    """

    def __init__(self, repository: CustomerRepository | None = None) -> None:
        self._repo: CustomerRepository = repository or CustomerRepository()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        """Return every customer serialised to a dictionary.

        Returns:
            list[dict]: All customers ordered by ascending ID.
        """
        return [c.to_dict() for c in self._repo.get_all()]

    def get_by_id(self, customer_id: int) -> dict:
        """Return a single customer by primary key.

        Args:
            customer_id (int): ID to look up.

        Returns:
            dict: Serialised customer record.

        Raises:
            CustomerNotFoundError: If *customer_id* does not exist.
        """
        customer = self._repo.get_by_id(customer_id)
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        return customer.to_dict()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create(self, data: dict[str, Any]) -> dict:
        """Create and persist a new customer from validated input.

        Args:
            data (dict): Must contain ``name``, ``email``, ``phone``,
                and ``address`` keys with non-blank string values.

        Returns:
            dict: The newly created and persisted customer record.

        Raises:
            ValidationError: If any required field is absent or blank.
            EmailAlreadyExistsError: If the email is already registered.
        """
        self._validate_required_fields(data)

        email = data["email"].strip().lower()
        if self._repo.get_by_email(email) is not None:
            raise EmailAlreadyExistsError(email)

        customer = Customer(
            name=data["name"].strip(),
            email=email,
            phone=data["phone"].strip(),
            address=data["address"].strip(),
        )
        saved = self._repo.add(customer)
        return saved.to_dict()

    def update(self, customer_id: int, data: dict[str, Any]) -> dict:
        """Partially update an existing customer (PATCH semantics).

        Only keys supplied in *data* are modified; all other fields
        remain unchanged.  Unknown keys are silently ignored.

        Args:
            customer_id (int): ID of the customer to update.
            data (dict): Subset of ``name``, ``email``, ``phone``,
                ``address`` to overwrite.

        Returns:
            dict: The updated customer record after persistence.

        Raises:
            CustomerNotFoundError: If *customer_id* does not exist.
            EmailAlreadyExistsError: If the new email is already taken
                by a different customer.
        """
        customer = self._repo.get_by_id(customer_id)
        if customer is None:
            raise CustomerNotFoundError(customer_id)

        if "name" in data and data["name"].strip():
            customer.name = data["name"].strip()

        if "phone" in data and data["phone"].strip():
            customer.phone = data["phone"].strip()

        if "address" in data and data["address"].strip():
            customer.address = data["address"].strip()

        if "email" in data:
            new_email = data["email"].strip().lower()
            if new_email != customer.email:
                existing = self._repo.get_by_email(new_email)
                if existing is not None:
                    raise EmailAlreadyExistsError(new_email)
                customer.email = new_email

        saved = self._repo.save(customer)
        return saved.to_dict()

    def delete(self, customer_id: int) -> None:
        """Delete a customer by primary key.

        Args:
            customer_id (int): ID of the customer to remove.

        Raises:
            CustomerNotFoundError: If *customer_id* does not exist.
        """
        customer = self._repo.get_by_id(customer_id)
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        self._repo.delete(customer)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_required_fields(data: dict[str, Any]) -> None:
        """Ensure all required fields are present and contain non-blank values.

        Args:
            data (dict): Raw input dictionary from the caller.

        Raises:
            ValidationError: Lists all missing / blank fields in the
                exception message.
        """
        missing = [f for f in _REQUIRED_FIELDS if not str(data.get(f, "")).strip()]
        if missing:
            raise ValidationError(
                f"Missing or blank required field(s): {', '.join(sorted(missing))}."
            )
