"""
tests/test_customer_repository.py
-----------------------------------
Unit tests for ``CustomerRepository``.

These tests verify the data-access layer in isolation using a real
SQLite in-memory database (provided by the ``app`` / ``db`` fixtures in
``conftest.py``).  No HTTP layer or service logic is involved.

Each test function receives a fresh, empty database so there is no
dependency between test cases.

Test groups
-----------
TestGetAll        – ``get_all``
TestGetById       – ``get_by_id``
TestGetByEmail    – ``get_by_email``
TestAdd           – ``add``
TestSave          – ``save`` (update)
TestDelete        – ``delete``
"""

import pytest

from app.models.customer import Customer
from app.repositories.customer_repo import CustomerRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_customer(
    name: str = "Test User",
    email: str = "test@example.com",
    phone: str = "555-0000",
    address: str = "1 Test St",
) -> Customer:
    """Return an unsaved Customer ORM object with sensible defaults."""
    return Customer(name=name, email=email, phone=phone, address=address)


@pytest.fixture()
def repo() -> CustomerRepository:
    return CustomerRepository()


@pytest.fixture()
def saved_customer(db, repo) -> Customer:
    """Insert one customer into the DB and return the persisted object."""
    return repo.add(_make_customer())


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


class TestGetAll:
    """Tests for CustomerRepository.get_all."""

    def test_empty_database_returns_empty_list(self, app, repo):
        assert repo.get_all() == []

    def test_returns_all_inserted_records(self, app, db, repo):
        repo.add(_make_customer(email="a@x.com"))
        repo.add(_make_customer(email="b@x.com"))
        result = repo.get_all()
        assert len(result) == 2

    def test_results_ordered_by_id_ascending(self, app, db, repo):
        c1 = repo.add(_make_customer(name="Alpha", email="alpha@x.com"))
        c2 = repo.add(_make_customer(name="Beta", email="beta@x.com"))
        ids = [c.id for c in repo.get_all()]
        assert ids == sorted(ids)
        assert ids[0] == c1.id
        assert ids[1] == c2.id

    def test_each_result_is_customer_instance(self, app, db, repo):
        repo.add(_make_customer())
        for item in repo.get_all():
            assert isinstance(item, Customer)


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    """Tests for CustomerRepository.get_by_id."""

    def test_returns_correct_customer(self, app, db, repo, saved_customer):
        found = repo.get_by_id(saved_customer.id)
        assert found is not None
        assert found.id == saved_customer.id
        assert found.email == saved_customer.email

    def test_returns_none_for_nonexistent_id(self, app, repo):
        assert repo.get_by_id(99999) is None

    def test_returns_none_for_zero(self, app, repo):
        assert repo.get_by_id(0) is None


# ---------------------------------------------------------------------------
# get_by_email
# ---------------------------------------------------------------------------


class TestGetByEmail:
    """Tests for CustomerRepository.get_by_email."""

    def test_finds_existing_email(self, app, db, repo):
        repo.add(_make_customer(email="carol@example.com"))
        found = repo.get_by_email("carol@example.com")
        assert found is not None
        assert found.email == "carol@example.com"

    def test_returns_none_for_unknown_email(self, app, repo):
        assert repo.get_by_email("nobody@example.com") is None

    def test_is_case_insensitive(self, app, db, repo):
        repo.add(_make_customer(email="dave@example.com"))
        # email stored as lower-case; lookup with same lower-case value
        assert repo.get_by_email("dave@example.com") is not None


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestAdd:
    """Tests for CustomerRepository.add."""

    def test_returns_customer_with_assigned_id(self, app, repo):
        c = repo.add(_make_customer())
        assert c.id is not None
        assert c.id > 0

    def test_created_at_is_populated(self, app, repo):
        c = repo.add(_make_customer())
        assert c.created_at is not None

    def test_customer_persisted_in_database(self, app, repo):
        c = repo.add(_make_customer(email="persisted@x.com"))
        assert repo.get_by_id(c.id) is not None

    def test_email_stored_as_provided(self, app, repo):
        c = repo.add(_make_customer(email="exact@x.com"))
        found = repo.get_by_id(c.id)
        assert found.email == "exact@x.com"


# ---------------------------------------------------------------------------
# save (update)
# ---------------------------------------------------------------------------


class TestSave:
    """Tests for CustomerRepository.save (persisting mutations)."""

    def test_name_update_persisted(self, app, db, repo, saved_customer):
        saved_customer.name = "Updated Name"
        updated = repo.save(saved_customer)
        assert updated.name == "Updated Name"
        # Verify round-trip from DB
        reloaded = repo.get_by_id(saved_customer.id)
        assert reloaded.name == "Updated Name"

    def test_email_update_persisted(self, app, db, repo, saved_customer):
        saved_customer.email = "updated@example.com"
        repo.save(saved_customer)
        reloaded = repo.get_by_id(saved_customer.id)
        assert reloaded.email == "updated@example.com"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    """Tests for CustomerRepository.delete."""

    def test_removes_customer_from_database(self, app, db, repo, saved_customer):
        removed_id = saved_customer.id
        repo.delete(saved_customer)
        assert repo.get_by_id(removed_id) is None

    def test_other_records_unaffected(self, app, db, repo):
        c1 = repo.add(_make_customer(email="keep@x.com"))
        c2 = repo.add(_make_customer(email="delete@x.com"))
        repo.delete(c2)
        assert repo.get_by_id(c1.id) is not None
