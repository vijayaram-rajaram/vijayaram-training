"""
tests/test_customer_routes.py
------------------------------
Integration tests for the Customer CRUD REST API endpoints.

Each test uses Flask's built-in test client so the full HTTP stack
(routing, serialisation, status codes, response envelope) is exercised
without starting a real server.

The ``client`` and ``db`` fixtures (from ``conftest.py``) provide a
fresh in-memory SQLite database per test, ensuring full isolation.

Test groups
-----------
TestListCustomers     – GET  /api/customers
TestGetCustomer       – GET  /api/customers/<id>
TestCreateCustomer    – POST /api/customers
TestUpdateCustomer    – PUT  /api/customers/<id>
TestDeleteCustomer    – DELETE /api/customers/<id>
"""

import json

import pytest

from app.models.customer import Customer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_json(client, url: str, payload: dict):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def _put_json(client, url: str, payload: dict):
    return client.put(url, data=json.dumps(payload), content_type="application/json")


def _json(response) -> dict:
    return json.loads(response.data)


def _seed(db, count: int = 3) -> list[Customer]:
    """Insert *count* customers and return them."""
    customers = []
    for i in range(1, count + 1):
        c = Customer(
            name=f"User {i}",
            email=f"user{i}@example.com",
            phone=f"555-000{i}",
            address=f"{i} Test St",
        )
        db.session.add(c)
    db.session.commit()
    customers = db.session.query(Customer).order_by(Customer.id).all()
    return customers


BASE = "/api/customers"


# ---------------------------------------------------------------------------
# GET /api/customers
# ---------------------------------------------------------------------------


class TestListCustomers:
    """Tests for GET /api/customers."""

    def test_status_200_on_empty_db(self, client, db):
        response = client.get(BASE)
        assert response.status_code == 200

    def test_envelope_status_success(self, client, db):
        body = _json(client.get(BASE))
        assert body["status"] == "success"

    def test_count_matches_seeded_records(self, client, db):
        _seed(db, 3)
        body = _json(client.get(BASE))
        assert body["count"] == 3
        assert len(body["data"]) == 3

    def test_returns_expected_fields(self, client, db):
        _seed(db, 1)
        body = _json(client.get(BASE))
        customer = body["data"][0]
        assert {"id", "name", "email", "phone", "address", "created_at"}.issubset(
            customer.keys()
        )

    def test_empty_database_returns_empty_list(self, client, db):
        body = _json(client.get(BASE))
        assert body["data"] == []
        assert body["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/customers/<id>
# ---------------------------------------------------------------------------


class TestGetCustomer:
    """Tests for GET /api/customers/<id>."""

    def test_status_200_for_existing_customer(self, client, db):
        seeded = _seed(db, 1)
        response = client.get(f"{BASE}/{seeded[0].id}")
        assert response.status_code == 200

    def test_returns_correct_customer(self, client, db):
        seeded = _seed(db, 2)
        body = _json(client.get(f"{BASE}/{seeded[1].id}"))
        assert body["data"]["email"] == "user2@example.com"

    def test_status_404_for_missing_customer(self, client, db):
        response = client.get(f"{BASE}/99999")
        assert response.status_code == 404

    def test_404_body_has_error_status(self, client, db):
        body = _json(client.get(f"{BASE}/99999"))
        assert body["status"] == "error"
        assert "99999" in body["message"]


# ---------------------------------------------------------------------------
# POST /api/customers
# ---------------------------------------------------------------------------


_NEW_CUSTOMER = {
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "phone": "555-9999",
    "address": "1 Example Lane, Austin, TX",
}


class TestCreateCustomer:
    """Tests for POST /api/customers."""

    def test_status_201_on_success(self, client, db):
        response = _post_json(client, BASE, _NEW_CUSTOMER)
        assert response.status_code == 201

    def test_response_contains_id(self, client, db):
        body = _json(_post_json(client, BASE, _NEW_CUSTOMER))
        assert "id" in body["data"]
        assert body["data"]["id"] is not None

    def test_email_stored_lowercased(self, client, db):
        payload = {**_NEW_CUSTOMER, "email": "JANE.DOE@EXAMPLE.COM"}
        body = _json(_post_json(client, BASE, payload))
        assert body["data"]["email"] == "jane.doe@example.com"

    def test_status_400_for_non_json_body(self, client, db):
        response = client.post(BASE, data="not json", content_type="text/plain")
        assert response.status_code == 400

    def test_status_422_for_missing_required_field(self, client, db):
        payload = {k: v for k, v in _NEW_CUSTOMER.items() if k != "email"}
        response = _post_json(client, BASE, payload)
        assert response.status_code == 422

    def test_status_422_for_duplicate_email(self, client, db):
        _post_json(client, BASE, _NEW_CUSTOMER)
        response = _post_json(client, BASE, _NEW_CUSTOMER)
        assert response.status_code == 422

    def test_error_message_on_duplicate_email(self, client, db):
        _post_json(client, BASE, _NEW_CUSTOMER)
        body = _json(_post_json(client, BASE, _NEW_CUSTOMER))
        assert body["status"] == "error"
        assert "jane.doe@example.com" in body["message"]

    def test_record_persisted_after_create(self, client, db):
        create_body = _json(_post_json(client, BASE, _NEW_CUSTOMER))
        new_id = create_body["data"]["id"]
        get_body = _json(client.get(f"{BASE}/{new_id}"))
        assert get_body["data"]["name"] == "Jane Doe"


# ---------------------------------------------------------------------------
# PUT /api/customers/<id>
# ---------------------------------------------------------------------------


class TestUpdateCustomer:
    """Tests for PUT /api/customers/<id>."""

    def test_status_200_on_success(self, client, db):
        seeded = _seed(db, 1)
        response = _put_json(client, f"{BASE}/{seeded[0].id}", {"phone": "999-0000"})
        assert response.status_code == 200

    def test_field_updated_in_response(self, client, db):
        seeded = _seed(db, 1)
        body = _json(_put_json(client, f"{BASE}/{seeded[0].id}", {"name": "Updated"}))
        assert body["data"]["name"] == "Updated"

    def test_untouched_fields_unchanged(self, client, db):
        seeded = _seed(db, 1)
        original_email = seeded[0].email
        _put_json(client, f"{BASE}/{seeded[0].id}", {"phone": "000-0000"})
        body = _json(client.get(f"{BASE}/{seeded[0].id}"))
        assert body["data"]["email"] == original_email

    def test_status_404_for_missing_customer(self, client, db):
        response = _put_json(client, f"{BASE}/99999", {"phone": "000-0000"})
        assert response.status_code == 404

    def test_status_422_for_duplicate_email(self, client, db):
        seeded = _seed(db, 2)
        response = _put_json(
            client,
            f"{BASE}/{seeded[0].id}",
            {"email": seeded[1].email},
        )
        assert response.status_code == 422

    def test_status_400_for_missing_body(self, client, db):
        seeded = _seed(db, 1)
        response = client.put(f"{BASE}/{seeded[0].id}", content_type="application/json")
        assert response.status_code == 400

    def test_keeping_own_email_does_not_conflict(self, client, db):
        seeded = _seed(db, 1)
        response = _put_json(
            client,
            f"{BASE}/{seeded[0].id}",
            {"email": seeded[0].email, "phone": "888-0000"},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/customers/<id>
# ---------------------------------------------------------------------------


class TestDeleteCustomer:
    """Tests for DELETE /api/customers/<id>."""

    def test_status_200_on_success(self, client, db):
        seeded = _seed(db, 1)
        response = client.delete(f"{BASE}/{seeded[0].id}")
        assert response.status_code == 200

    def test_success_message_contains_id(self, client, db):
        seeded = _seed(db, 1)
        body = _json(client.delete(f"{BASE}/{seeded[0].id}"))
        assert str(seeded[0].id) in body["message"]

    def test_record_removed_after_delete(self, client, db):
        seeded = _seed(db, 1)
        customer_id = seeded[0].id
        client.delete(f"{BASE}/{customer_id}")
        response = client.get(f"{BASE}/{customer_id}")
        assert response.status_code == 404

    def test_status_404_for_missing_customer(self, client, db):
        response = client.delete(f"{BASE}/99999")
        assert response.status_code == 404

    def test_404_body_has_error_status(self, client, db):
        body = _json(client.delete(f"{BASE}/99999"))
        assert body["status"] == "error"
