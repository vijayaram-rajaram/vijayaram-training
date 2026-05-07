"""
tests/test_customer_routes.py
------------------------------
Integration tests for the Customer CRUD REST API endpoints.

Each test uses Flask's built-in test client so the full HTTP stack
(routing, serialisation, status codes, response envelope) is exercised
without starting a real server.

``mock_data.reset_store()`` is called in ``setUp`` to guarantee a clean
5-record state before every test case.
"""

import json
import unittest

from app import create_app
from app.data import mock_data

SEED_COUNT = 5


class BaseTestCase(unittest.TestCase):
    """Base class that wires up the Flask test client and resets state."""

    def setUp(self):
        mock_data.reset_store()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def _get(self, url: str):
        return self.client.get(url)

    def _post(self, url: str, payload: dict):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _put(self, url: str, payload: dict):
        return self.client.put(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _delete(self, url: str):
        return self.client.delete(url)

    @staticmethod
    def _json(response) -> dict:
        """Return the parsed JSON body of a response."""
        return json.loads(response.data)


# ---------------------------------------------------------------------------
# GET /api/customers
# ---------------------------------------------------------------------------


class TestListCustomers(BaseTestCase):
    """Tests for GET /api/customers."""

    def test_status_200(self):
        """Listing customers should return HTTP 200."""
        response = self._get("/api/customers")
        self.assertEqual(response.status_code, 200)

    def test_response_envelope_status_success(self):
        """Response envelope must have status='success'."""
        body = self._json(self._get("/api/customers"))
        self.assertEqual(body["status"], "success")

    def test_count_matches_seed(self):
        """count field must equal the number of seed records."""
        body = self._json(self._get("/api/customers"))
        self.assertEqual(body["count"], SEED_COUNT)

    def test_data_is_list(self):
        """data field must be a list."""
        body = self._json(self._get("/api/customers"))
        self.assertIsInstance(body["data"], list)

    def test_data_length_matches_count(self):
        """The length of data must equal count."""
        body = self._json(self._get("/api/customers"))
        self.assertEqual(len(body["data"]), body["count"])


# ---------------------------------------------------------------------------
# GET /api/customers/<id>
# ---------------------------------------------------------------------------


class TestGetCustomer(BaseTestCase):
    """Tests for GET /api/customers/<id>."""

    def test_existing_id_returns_200(self):
        """A valid customer ID must return 200."""
        response = self._get("/api/customers/1")
        self.assertEqual(response.status_code, 200)

    def test_existing_id_returns_correct_data(self):
        """The correct customer should be returned for the given ID."""
        body = self._json(self._get("/api/customers/1"))
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["id"], 1)
        self.assertEqual(body["data"]["name"], "Alice Johnson")

    def test_missing_id_returns_404(self):
        """A non-existent customer ID must return 404."""
        response = self._get("/api/customers/9999")
        self.assertEqual(response.status_code, 404)

    def test_missing_id_body_has_error_status(self):
        """404 response body must carry status='error'."""
        body = self._json(self._get("/api/customers/9999"))
        self.assertEqual(body["status"], "error")

    def test_missing_id_body_contains_message(self):
        """404 body should mention the requested ID in the message."""
        body = self._json(self._get("/api/customers/9999"))
        self.assertIn("9999", body["message"])


# ---------------------------------------------------------------------------
# POST /api/customers
# ---------------------------------------------------------------------------


class TestCreateCustomer(BaseTestCase):
    """Tests for POST /api/customers."""

    _VALID = {
        "name": "Grace Hopper",
        "email": "grace.hopper@example.com",
        "phone": "555-0300",
        "address": "1 Navy Yard, Washington, DC",
    }

    def test_valid_payload_returns_201(self):
        """A valid create request should return 201 Created."""
        response = self._post("/api/customers", self._VALID)
        self.assertEqual(response.status_code, 201)

    def test_valid_payload_returns_success_status(self):
        """Response envelope must have status='success'."""
        body = self._json(self._post("/api/customers", self._VALID))
        self.assertEqual(body["status"], "success")

    def test_created_customer_has_id(self):
        """The created customer dict must include an integer id."""
        body = self._json(self._post("/api/customers", self._VALID))
        self.assertIn("id", body["data"])
        self.assertIsInstance(body["data"]["id"], int)

    def test_created_email_normalised(self):
        """Email in response must be lowercase."""
        payload = dict(self._VALID, email="GRACE@EXAMPLE.COM")
        body = self._json(self._post("/api/customers", payload))
        self.assertEqual(body["data"]["email"], "grace@example.com")

    def test_list_grows_after_create(self):
        """Customer count should increase by 1 after a successful create."""
        self._post("/api/customers", self._VALID)
        body = self._json(self._get("/api/customers"))
        self.assertEqual(body["count"], SEED_COUNT + 1)

    def test_missing_field_returns_422(self):
        """Payload missing a required field should return 422."""
        payload = {k: v for k, v in self._VALID.items() if k != "email"}
        response = self._post("/api/customers", payload)
        self.assertEqual(response.status_code, 422)

    def test_duplicate_email_returns_422(self):
        """Duplicate email on create should return 422."""
        self._post("/api/customers", self._VALID)
        response = self._post("/api/customers", self._VALID)
        self.assertEqual(response.status_code, 422)

    def test_no_body_returns_400(self):
        """A request with no JSON body should return 400."""
        response = self.client.post("/api/customers")
        self.assertEqual(response.status_code, 400)

    def test_empty_json_object_returns_422(self):
        """An empty JSON body {} should return 422 (missing required fields)."""
        response = self._post("/api/customers", {})
        self.assertEqual(response.status_code, 422)


# ---------------------------------------------------------------------------
# PUT /api/customers/<id>
# ---------------------------------------------------------------------------


class TestUpdateCustomer(BaseTestCase):
    """Tests for PUT /api/customers/<id>."""

    def test_valid_update_returns_200(self):
        """Updating an existing customer should return 200."""
        response = self._put("/api/customers/1", {"phone": "555-9999"})
        self.assertEqual(response.status_code, 200)

    def test_update_reflects_new_value(self):
        """The updated field should appear in the response data."""
        body = self._json(self._put("/api/customers/1", {"phone": "555-9999"}))
        self.assertEqual(body["data"]["phone"], "555-9999")

    def test_update_preserves_other_fields(self):
        """Fields not in the payload must remain unchanged."""
        original = self._json(self._get("/api/customers/2"))["data"]
        self._put("/api/customers/2", {"phone": "000-0000"})
        updated = self._json(self._get("/api/customers/2"))["data"]
        self.assertEqual(updated["name"], original["name"])
        self.assertEqual(updated["email"], original["email"])
        self.assertEqual(updated["address"], original["address"])

    def test_update_nonexistent_returns_404(self):
        """Updating a non-existent customer should return 404."""
        response = self._put("/api/customers/9999", {"name": "Nobody"})
        self.assertEqual(response.status_code, 404)

    def test_update_duplicate_email_returns_422(self):
        """Changing email to an existing email should return 422."""
        response = self._put("/api/customers/1", {"email": "bob.smith@example.com"})
        self.assertEqual(response.status_code, 422)

    def test_update_same_email_returns_200(self):
        """Submitting the same email for the same customer should succeed."""
        original_email = self._json(self._get("/api/customers/1"))["data"]["email"]
        response = self._put("/api/customers/1", {"email": original_email})
        self.assertEqual(response.status_code, 200)

    def test_no_body_returns_400(self):
        """PUT with no JSON body should return 400."""
        response = self.client.put("/api/customers/1")
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# DELETE /api/customers/<id>
# ---------------------------------------------------------------------------


class TestDeleteCustomer(BaseTestCase):
    """Tests for DELETE /api/customers/<id>."""

    def test_existing_delete_returns_200(self):
        """Deleting an existing customer should return 200."""
        response = self._delete("/api/customers/1")
        self.assertEqual(response.status_code, 200)

    def test_delete_success_message(self):
        """Response body should confirm the deletion with status='success'."""
        body = self._json(self._delete("/api/customers/1"))
        self.assertEqual(body["status"], "success")

    def test_deleted_customer_not_retrievable(self):
        """After deletion, GET on that ID should return 404."""
        self._delete("/api/customers/1")
        response = self._get("/api/customers/1")
        self.assertEqual(response.status_code, 404)

    def test_delete_reduces_count(self):
        """Customer list count should decrease by 1 after deletion."""
        self._delete("/api/customers/1")
        body = self._json(self._get("/api/customers"))
        self.assertEqual(body["count"], SEED_COUNT - 1)

    def test_delete_nonexistent_returns_404(self):
        """Deleting a non-existent customer should return 404."""
        response = self._delete("/api/customers/9999")
        self.assertEqual(response.status_code, 404)

    def test_double_delete_second_returns_404(self):
        """Deleting the same ID twice should return 404 on the second call."""
        self._delete("/api/customers/3")
        response = self._delete("/api/customers/3")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
