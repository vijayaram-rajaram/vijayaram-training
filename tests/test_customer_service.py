"""
tests/test_customer_service.py
--------------------------------
Unit tests for CustomerService.

The test suite covers every public method of CustomerService and validates
both the happy path and all documented error conditions.

Each test calls ``mock_data.reset_store()`` in ``setUp`` to ensure a
deterministic, isolated starting state (5 seed customers with IDs 1–5).
"""

import unittest

from app.data import mock_data
from app.services.customer_service import CustomerService

# Number of records in the seed data (see app/data/mock_data.py)
SEED_COUNT = 5


class TestGetAll(unittest.TestCase):
    """Tests for CustomerService.get_all."""

    def setUp(self):
        mock_data.reset_store()
        self.service = CustomerService()

    def test_returns_list(self):
        """get_all should return a list."""
        result = self.service.get_all()
        self.assertIsInstance(result, list)

    def test_returns_all_seed_records(self):
        """get_all should return every seeded customer."""
        result = self.service.get_all()
        self.assertEqual(len(result), SEED_COUNT)

    def test_each_item_is_dict(self):
        """Every item in the result should be a plain dictionary."""
        for item in self.service.get_all():
            with self.subTest(item=item):
                self.assertIsInstance(item, dict)

    def test_items_contain_required_keys(self):
        """Each customer dict must expose all model fields."""
        required_keys = {"id", "name", "email", "phone", "address", "created_at"}
        for item in self.service.get_all():
            with self.subTest(item=item):
                self.assertTrue(required_keys.issubset(item.keys()))


class TestGetById(unittest.TestCase):
    """Tests for CustomerService.get_by_id."""

    def setUp(self):
        mock_data.reset_store()
        self.service = CustomerService()

    def test_returns_existing_customer(self):
        """get_by_id should return the matching customer dict."""
        result = self.service.get_by_id(1)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 1)

    def test_name_matches_seed_data(self):
        """Customer 1 should be Alice Johnson from the seed data."""
        result = self.service.get_by_id(1)
        self.assertEqual(result["name"], "Alice Johnson")

    def test_returns_none_for_missing_id(self):
        """get_by_id should return None when the ID does not exist."""
        result = self.service.get_by_id(9999)
        self.assertIsNone(result)

    def test_returns_none_for_zero_id(self):
        """ID 0 does not exist in the seed data."""
        result = self.service.get_by_id(0)
        self.assertIsNone(result)


class TestCreate(unittest.TestCase):
    """Tests for CustomerService.create."""

    def setUp(self):
        mock_data.reset_store()
        self.service = CustomerService()
        self.valid_payload = {
            "name": "Frank Castle",
            "email": "frank.castle@example.com",
            "phone": "555-0200",
            "address": "10 Hell's Kitchen, New York, NY",
        }

    def test_create_returns_dict(self):
        """create should return a dict representing the new customer."""
        result = self.service.create(self.valid_payload)
        self.assertIsInstance(result, dict)

    def test_create_assigns_new_id(self):
        """The new customer should receive an ID greater than 5."""
        result = self.service.create(self.valid_payload)
        self.assertGreater(result["id"], SEED_COUNT)

    def test_create_persists_record(self):
        """After creation the record must be retrievable."""
        created = self.service.create(self.valid_payload)
        fetched = self.service.get_by_id(created["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["email"], "frank.castle@example.com")

    def test_create_increments_total_count(self):
        """Total customer count should increase by 1 after creation."""
        self.service.create(self.valid_payload)
        self.assertEqual(len(self.service.get_all()), SEED_COUNT + 1)

    def test_create_normalises_email_to_lowercase(self):
        """Emails should be stored in lowercase."""
        payload = dict(self.valid_payload, email="UPPER@EXAMPLE.COM")
        result = self.service.create(payload)
        self.assertEqual(result["email"], "upper@example.com")

    def test_create_raises_on_missing_name(self):
        """ValueError must be raised when 'name' is absent."""
        payload = {k: v for k, v in self.valid_payload.items() if k != "name"}
        with self.assertRaises(ValueError):
            self.service.create(payload)

    def test_create_raises_on_missing_email(self):
        """ValueError must be raised when 'email' is absent."""
        payload = {k: v for k, v in self.valid_payload.items() if k != "email"}
        with self.assertRaises(ValueError):
            self.service.create(payload)

    def test_create_raises_on_missing_phone(self):
        """ValueError must be raised when 'phone' is absent."""
        payload = {k: v for k, v in self.valid_payload.items() if k != "phone"}
        with self.assertRaises(ValueError):
            self.service.create(payload)

    def test_create_raises_on_missing_address(self):
        """ValueError must be raised when 'address' is absent."""
        payload = {k: v for k, v in self.valid_payload.items() if k != "address"}
        with self.assertRaises(ValueError):
            self.service.create(payload)

    def test_create_raises_on_duplicate_email(self):
        """Creating two customers with the same email must raise ValueError."""
        self.service.create(self.valid_payload)
        with self.assertRaises(ValueError):
            self.service.create(self.valid_payload)

    def test_create_error_message_mentions_duplicate_email(self):
        """The duplicate-email error message should name the address."""
        self.service.create(self.valid_payload)
        with self.assertRaises(ValueError) as ctx:
            self.service.create(self.valid_payload)
        self.assertIn("frank.castle@example.com", str(ctx.exception))


class TestUpdate(unittest.TestCase):
    """Tests for CustomerService.update."""

    def setUp(self):
        mock_data.reset_store()
        self.service = CustomerService()

    def test_update_phone_returns_updated_dict(self):
        """update should return the modified customer dict."""
        result = self.service.update(1, {"phone": "555-9999"})
        self.assertIsNotNone(result)
        self.assertEqual(result["phone"], "555-9999")

    def test_update_name(self):
        """Updating the name field should be reflected in get_by_id."""
        self.service.update(1, {"name": "Alicia Johnson"})
        fetched = self.service.get_by_id(1)
        self.assertEqual(fetched["name"], "Alicia Johnson")

    def test_update_address(self):
        """Updating address should persist."""
        self.service.update(2, {"address": "999 New St, Boston, MA"})
        fetched = self.service.get_by_id(2)
        self.assertEqual(fetched["address"], "999 New St, Boston, MA")

    def test_update_email_normalised_to_lowercase(self):
        """Updated emails should be normalised to lowercase."""
        self.service.update(1, {"email": "ALICE.NEW@EXAMPLE.COM"})
        fetched = self.service.get_by_id(1)
        self.assertEqual(fetched["email"], "alice.new@example.com")

    def test_update_preserves_unchanged_fields(self):
        """Fields not included in the update payload should remain unchanged."""
        original = self.service.get_by_id(3)
        self.service.update(3, {"phone": "000-0000"})
        updated = self.service.get_by_id(3)
        self.assertEqual(updated["name"], original["name"])
        self.assertEqual(updated["email"], original["email"])
        self.assertEqual(updated["address"], original["address"])

    def test_update_returns_none_for_missing_id(self):
        """update should return None when the customer does not exist."""
        result = self.service.update(9999, {"name": "Ghost"})
        self.assertIsNone(result)

    def test_update_raises_on_duplicate_email(self):
        """Changing email to one already used by another customer raises ValueError."""
        # Customer 2's email is bob.smith@example.com
        with self.assertRaises(ValueError):
            self.service.update(1, {"email": "bob.smith@example.com"})

    def test_update_same_email_allowed(self):
        """A customer may be updated keeping their own existing email."""
        original = self.service.get_by_id(1)
        result = self.service.update(1, {"email": original["email"], "phone": "999-9999"})
        self.assertIsNotNone(result)
        self.assertEqual(result["email"], original["email"])


class TestDelete(unittest.TestCase):
    """Tests for CustomerService.delete."""

    def setUp(self):
        mock_data.reset_store()
        self.service = CustomerService()

    def test_delete_existing_returns_true(self):
        """Deleting an existing customer should return True."""
        result = self.service.delete(1)
        self.assertTrue(result)

    def test_delete_reduces_count(self):
        """Customer count should decrease by 1 after deletion."""
        self.service.delete(1)
        self.assertEqual(len(self.service.get_all()), SEED_COUNT - 1)

    def test_delete_makes_id_unreachable(self):
        """After deletion, get_by_id should return None for that ID."""
        self.service.delete(2)
        self.assertIsNone(self.service.get_by_id(2))

    def test_delete_nonexistent_returns_false(self):
        """Deleting an ID that does not exist should return False."""
        result = self.service.delete(9999)
        self.assertFalse(result)

    def test_double_delete_returns_false(self):
        """Deleting the same ID twice: first True, second False."""
        self.assertTrue(self.service.delete(3))
        self.assertFalse(self.service.delete(3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
