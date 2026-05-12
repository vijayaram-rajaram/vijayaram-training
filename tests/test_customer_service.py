"""
tests/test_customer_service.py
--------------------------------
Unit tests for ``CustomerService``.

The repository is replaced with a ``MagicMock`` so these tests exercise
*only* the service's business logic (validation, exception raising,
delegation) without touching a real database.  This makes the suite fast
and independent of any infrastructure.

Test groups
-----------
TestGetAll              – ``get_all``
TestGetById             – ``get_by_id``
TestCreate              – ``create``
TestCreate_Validation   – ``create`` validation rules
TestUpdate              – ``update``
TestDelete              – ``delete``
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.exceptions import CustomerNotFoundError, EmailAlreadyExistsError, ValidationError
from app.repositories.customer_repo import CustomerRepository
from app.services.customer_service import CustomerService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_customer(
    id: int = 1,
    name: str = "Alice Johnson",
    email: str = "alice@example.com",
    phone: str = "555-0101",
    address: str = "1 Main St",
) -> MagicMock:
    """Return a MagicMock that mimics a Customer ORM object.

    ``spec=Customer`` is intentionally omitted: Flask-SQLAlchemy's query
    descriptor fires during spec introspection outside an app context,
    causing a ``RuntimeError``.  Using a plain MagicMock is safe and
    sufficient for testing the service layer.
    """
    m = MagicMock()
    m.id = id
    m.name = name
    m.email = email
    m.phone = phone
    m.address = address
    m.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    m.to_dict.return_value = {
        "id": id,
        "name": name,
        "email": email,
        "phone": phone,
        "address": address,
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    return m


@pytest.fixture()
def mock_repo() -> MagicMock:
    """Return a MagicMock with the same spec as CustomerRepository."""
    return MagicMock(spec=CustomerRepository)


@pytest.fixture()
def service(mock_repo) -> CustomerService:
    """CustomerService under test, injected with the mock repository."""
    return CustomerService(repository=mock_repo)


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


class TestGetAll:
    """Tests for CustomerService.get_all."""

    def test_returns_serialised_list(self, service, mock_repo):
        mock_repo.get_all.return_value = [_mock_customer(id=1), _mock_customer(id=2)]
        result = service.get_all()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_each_item_is_dict(self, service, mock_repo):
        mock_repo.get_all.return_value = [_mock_customer()]
        for item in service.get_all():
            assert isinstance(item, dict)

    def test_empty_repository_returns_empty_list(self, service, mock_repo):
        mock_repo.get_all.return_value = []
        assert service.get_all() == []

    def test_delegates_to_repository_get_all(self, service, mock_repo):
        mock_repo.get_all.return_value = []
        service.get_all()
        mock_repo.get_all.assert_called_once()


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    """Tests for CustomerService.get_by_id."""

    def test_returns_dict_for_existing_id(self, service, mock_repo):
        mock_repo.get_by_id.return_value = _mock_customer(id=1)
        result = service.get_by_id(1)
        assert isinstance(result, dict)
        assert result["id"] == 1

    def test_raises_customer_not_found_error(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(CustomerNotFoundError) as exc_info:
            service.get_by_id(99)
        assert exc_info.value.customer_id == 99

    def test_error_message_contains_id(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(CustomerNotFoundError) as exc_info:
            service.get_by_id(42)
        assert "42" in str(exc_info.value)

    def test_delegates_to_repository_get_by_id(self, service, mock_repo):
        mock_repo.get_by_id.return_value = _mock_customer()
        service.get_by_id(1)
        mock_repo.get_by_id.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


_VALID_PAYLOAD = {
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "phone": "555-9999",
    "address": "1 Example Lane, Austin, TX",
}


class TestCreate:
    """Tests for CustomerService.create – happy path."""

    def test_returns_customer_dict(self, service, mock_repo):
        mock_repo.get_by_email.return_value = None
        mock_repo.add.return_value = _mock_customer(email="jane.doe@example.com")
        result = service.create(_VALID_PAYLOAD.copy())
        assert isinstance(result, dict)

    def test_email_is_lower_cased(self, service, mock_repo):
        mock_repo.get_by_email.return_value = None
        created = _mock_customer(email="jane.doe@example.com")
        mock_repo.add.return_value = created
        service.create({**_VALID_PAYLOAD, "email": "Jane.Doe@EXAMPLE.com"})
        # Verify the Customer was built with a lower-cased email
        call_args = mock_repo.add.call_args[0][0]
        assert call_args.email == "jane.doe@example.com"

    def test_name_is_stripped(self, service, mock_repo):
        mock_repo.get_by_email.return_value = None
        mock_repo.add.return_value = _mock_customer()
        service.create({**_VALID_PAYLOAD, "name": "  Jane Doe  "})
        call_args = mock_repo.add.call_args[0][0]
        assert call_args.name == "Jane Doe"

    def test_delegates_add_to_repository(self, service, mock_repo):
        mock_repo.get_by_email.return_value = None
        mock_repo.add.return_value = _mock_customer()
        service.create(_VALID_PAYLOAD.copy())
        mock_repo.add.assert_called_once()


class TestCreate_Validation:
    """Tests for CustomerService.create – validation errors."""

    @pytest.mark.parametrize("missing_field", ["name", "email", "phone", "address"])
    def test_raises_validation_error_for_missing_field(self, missing_field, service, mock_repo):
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != missing_field}
        with pytest.raises(ValidationError):
            service.create(payload)

    @pytest.mark.parametrize("blank_field", ["name", "email", "phone", "address"])
    def test_raises_validation_error_for_blank_field(self, blank_field, service, mock_repo):
        payload = {**_VALID_PAYLOAD, blank_field: "   "}
        with pytest.raises(ValidationError):
            service.create(payload)

    def test_raises_email_already_exists_error(self, service, mock_repo):
        mock_repo.get_by_email.return_value = _mock_customer()
        with pytest.raises(EmailAlreadyExistsError) as exc_info:
            service.create(_VALID_PAYLOAD.copy())
        assert "jane.doe@example.com" in str(exc_info.value)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdate:
    """Tests for CustomerService.update."""

    def test_updates_name(self, service, mock_repo):
        customer = _mock_customer(id=1, name="Old Name")
        mock_repo.get_by_id.return_value = customer
        mock_repo.save.return_value = customer
        service.update(1, {"name": "New Name"})
        assert customer.name == "New Name"

    def test_updates_phone(self, service, mock_repo):
        customer = _mock_customer(id=1)
        mock_repo.get_by_id.return_value = customer
        mock_repo.save.return_value = customer
        service.update(1, {"phone": "555-9999"})
        assert customer.phone == "555-9999"

    def test_updates_email_when_unique(self, service, mock_repo):
        customer = _mock_customer(id=1, email="old@example.com")
        mock_repo.get_by_id.return_value = customer
        mock_repo.get_by_email.return_value = None
        mock_repo.save.return_value = customer
        service.update(1, {"email": "new@example.com"})
        assert customer.email == "new@example.com"

    def test_raises_customer_not_found_error(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(CustomerNotFoundError):
            service.update(99, {"name": "X"})

    def test_raises_email_already_exists_when_taken(self, service, mock_repo):
        customer = _mock_customer(id=1, email="old@example.com")
        other = _mock_customer(id=2, email="taken@example.com")
        mock_repo.get_by_id.return_value = customer
        mock_repo.get_by_email.return_value = other
        with pytest.raises(EmailAlreadyExistsError):
            service.update(1, {"email": "taken@example.com"})

    def test_no_email_conflict_keeping_same_email(self, service, mock_repo):
        """Updating with the customer's own email must not raise."""
        customer = _mock_customer(id=1, email="same@example.com")
        mock_repo.get_by_id.return_value = customer
        mock_repo.save.return_value = customer
        # Should NOT call get_by_email because email is unchanged
        service.update(1, {"email": "same@example.com"})
        mock_repo.get_by_email.assert_not_called()

    def test_blank_name_not_applied(self, service, mock_repo):
        customer = _mock_customer(id=1, name="Keep This")
        mock_repo.get_by_id.return_value = customer
        mock_repo.save.return_value = customer
        service.update(1, {"name": "   "})
        assert customer.name == "Keep This"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    """Tests for CustomerService.delete."""

    def test_calls_repository_delete(self, service, mock_repo):
        customer = _mock_customer()
        mock_repo.get_by_id.return_value = customer
        service.delete(1)
        mock_repo.delete.assert_called_once_with(customer)

    def test_raises_customer_not_found_error(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(CustomerNotFoundError) as exc_info:
            service.delete(99)
        assert exc_info.value.customer_id == 99

    def test_does_not_call_delete_when_not_found(self, service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(CustomerNotFoundError):
            service.delete(99)
        mock_repo.delete.assert_not_called()
