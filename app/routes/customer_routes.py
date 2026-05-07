"""
app/routes/customer_routes.py
------------------------------
Flask Blueprint that exposes the Customer CRUD REST API.

Endpoints
---------
GET    /api/customers           – List all customers
GET    /api/customers/<id>      – Retrieve a single customer
POST   /api/customers           – Create a new customer
PUT    /api/customers/<id>      – Update an existing customer
DELETE /api/customers/<id>      – Delete a customer

All responses use the envelope::

    {
        "status": "success" | "error",
        "data":   <payload>,          # present on success
        "message": "<description>"    # present on error
    }
"""

from flask import Blueprint, jsonify, request

from app.services.customer_service import CustomerService

customer_bp = Blueprint("customers", __name__, url_prefix="/api/customers")

_service = CustomerService()


# ---------------------------------------------------------------------------
# GET /api/customers
# ---------------------------------------------------------------------------


@customer_bp.route("", methods=["GET"])
def list_customers():
    """Return all customers.

    **GET /api/customers**

    Response 200::

        {
            "status": "success",
            "count": 5,
            "data": [ { ...customer }, ... ]
        }
    """
    customers = _service.get_all()
    return jsonify({"status": "success", "count": len(customers), "data": customers}), 200


# ---------------------------------------------------------------------------
# GET /api/customers/<id>
# ---------------------------------------------------------------------------


@customer_bp.route("/<int:customer_id>", methods=["GET"])
def get_customer(customer_id: int):
    """Return a single customer by ID.

    **GET /api/customers/<customer_id>**

    Response 200::

        { "status": "success", "data": { ...customer } }

    Response 404::

        { "status": "error", "message": "Customer 99 not found." }
    """
    customer = _service.get_by_id(customer_id)
    if customer is None:
        return _not_found(customer_id)
    return jsonify({"status": "success", "data": customer}), 200


# ---------------------------------------------------------------------------
# POST /api/customers
# ---------------------------------------------------------------------------


@customer_bp.route("", methods=["POST"])
def create_customer():
    """Create a new customer.

    **POST /api/customers**

    Request body (JSON)::

        {
            "name":    "Jane Doe",
            "email":   "jane@example.com",
            "phone":   "555-9999",
            "address": "1 Example Lane, Austin, TX"
        }

    Response 201::

        { "status": "success", "data": { ...customer } }

    Response 400 – missing or non-JSON body::

        { "status": "error", "message": "Request body must be valid JSON." }

    Response 422 – validation error::

        { "status": "error", "message": "<reason>" }
    """
    data = request.get_json(silent=True)
    if data is None:
        return _bad_request("Request body must be valid JSON.")
    try:
        customer = _service.create(data)
    except ValueError as exc:
        return _unprocessable(str(exc))
    return jsonify({"status": "success", "data": customer}), 201


# ---------------------------------------------------------------------------
# PUT /api/customers/<id>
# ---------------------------------------------------------------------------


@customer_bp.route("/<int:customer_id>", methods=["PUT"])
def update_customer(customer_id: int):
    """Update one or more fields of an existing customer.

    **PUT /api/customers/<customer_id>**

    Request body (JSON) – supply only the fields you wish to change::

        { "phone": "555-0000", "address": "New Address" }

    Response 200::

        { "status": "success", "data": { ...customer } }

    Response 400 – missing or non-JSON body.
    Response 404 – customer not found.
    Response 422 – validation error (e.g., duplicate email).
    """
    data = request.get_json(silent=True)
    if not data:
        return _bad_request("Request body must be valid JSON.")
    try:
        customer = _service.update(customer_id, data)
    except ValueError as exc:
        return _unprocessable(str(exc))
    if customer is None:
        return _not_found(customer_id)
    return jsonify({"status": "success", "data": customer}), 200


# ---------------------------------------------------------------------------
# DELETE /api/customers/<id>
# ---------------------------------------------------------------------------


@customer_bp.route("/<int:customer_id>", methods=["DELETE"])
def delete_customer(customer_id: int):
    """Delete a customer by ID.

    **DELETE /api/customers/<customer_id>**

    Response 200::

        { "status": "success", "message": "Customer 3 deleted." }

    Response 404::

        { "status": "error", "message": "Customer 99 not found." }
    """
    deleted = _service.delete(customer_id)
    if not deleted:
        return _not_found(customer_id)
    return jsonify({"status": "success", "message": f"Customer {customer_id} deleted."}), 200


# ---------------------------------------------------------------------------
# Private response helpers
# ---------------------------------------------------------------------------


def _not_found(customer_id: int):
    return jsonify({"status": "error", "message": f"Customer {customer_id} not found."}), 404


def _bad_request(message: str):
    return jsonify({"status": "error", "message": message}), 400


def _unprocessable(message: str):
    return jsonify({"status": "error", "message": message}), 422
