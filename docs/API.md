# Customer CRUD API — Documentation

## Overview

A RESTful API that manages **Customer** records backed by a **SQLite** database
(switchable to PostgreSQL or MySQL via the `DATABASE_URL` environment variable).

```
Base URL: http://127.0.0.1:5000
```

---

## Architecture

```
┌─────────────┐     HTTP      ┌──────────────────┐
│   Client    │──────────────▶│   Route layer     │  app/routes/
└─────────────┘               │  (Flask Blueprint) │
                               └────────┬─────────┘
                                        │ calls
                               ┌────────▼─────────┐
                               │  Service layer    │  app/services/
                               │  (business rules) │
                               └────────┬─────────┘
                                        │ delegates
                               ┌────────▼─────────┐
                               │ Repository layer  │  app/repositories/
                               │ (DB access only)  │
                               └────────┬─────────┘
                                        │ SQLAlchemy ORM
                               ┌────────▼─────────┐
                               │    Database       │  SQLite / PostgreSQL
                               └──────────────────┘
```

### Layer responsibilities

| Layer        | Module                       | Responsibility                                    |
|--------------|------------------------------|---------------------------------------------------|
| Routes       | `app/routes/customer_routes` | HTTP routing, request parsing, response envelope  |
| Service      | `app/services/customer_service` | Business rules, validation, domain exceptions  |
| Repository   | `app/repositories/customer_repo` | All SQLAlchemy queries, commit / rollback      |
| Model        | `app/models/customer`        | ORM mapping, `to_dict` serialisation             |
| Config       | `app/config`                 | Environment-based configuration                   |
| Exceptions   | `app/exceptions`             | Typed domain exceptions (`CustomerNotFoundError`, …) |

---

## Configuration

| Environment key | Default                  | Notes                                   |
|-----------------|--------------------------|-----------------------------------------|
| `DATABASE_URL`  | `sqlite:///customers_dev.db` | Any SQLAlchemy-compatible URI       |
| `FLASK_ENV`     | `development`            | `development` · `testing` · `production` |
| `SECRET_KEY`    | `dev-secret-…`           | **Override in production**              |

---

## Data Model

| Field        | Type     | Description                          | Required on create |
|--------------|----------|--------------------------------------|--------------------|
| `id`         | integer  | Auto-assigned unique identifier      | No (auto)          |
| `name`       | string   | Full name of the customer (≤ 255 chars) | **Yes**         |
| `email`      | string   | Unique, lower-cased email (≤ 255 chars) | **Yes**         |
| `phone`      | string   | Contact phone number (≤ 50 chars)    | **Yes**            |
| `address`    | string   | Physical address (≤ 500 chars)       | **Yes**            |
| `created_at` | datetime | UTC timestamp, ISO-8601 (auto-set)   | No (auto)          |

---

## Endpoints

### 1. List All Customers

```
GET /api/customers
```

**Response 200**

```json
{
  "status": "success",
  "count": 2,
  "data": [
    {
      "id": 1,
      "name": "Alice Johnson",
      "email": "alice.johnson@example.com",
      "phone": "555-0101",
      "address": "123 Main St, New York, NY 10001",
      "created_at": "2024-01-15T10:00:00+00:00"
    }
  ]
}
```

---

### 2. Retrieve a Customer

```
GET /api/customers/<id>
```

**Response 200**

```json
{
  "status": "success",
  "data": {
    "id": 1,
    "name": "Alice Johnson",
    "email": "alice.johnson@example.com",
    "phone": "555-0101",
    "address": "123 Main St, New York, NY 10001",
    "created_at": "2024-01-15T10:00:00+00:00"
  }
}
```

**Response 404**

```json
{
  "status": "error",
  "message": "Customer 99 not found."
}
```

---

### 3. Create a Customer

```
POST /api/customers
Content-Type: application/json
```

**Request body**

```json
{
  "name":    "Jane Doe",
  "email":   "jane.doe@example.com",
  "phone":   "555-9999",
  "address": "1 Example Lane, Austin, TX"
}
```

**Response 201**

```json
{
  "status": "success",
  "data": {
    "id": 3,
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "phone": "555-9999",
    "address": "1 Example Lane, Austin, TX",
    "created_at": "2026-05-09T12:00:00+00:00"
  }
}
```

**Response 400** — no JSON body or malformed JSON

```json
{ "status": "error", "message": "Request body must be valid JSON." }
```

**Response 422** — validation or conflict error

```json
{ "status": "error", "message": "Missing or blank required field(s): email." }
```

```json
{ "status": "error", "message": "Email 'jane.doe@example.com' is already registered." }
```

---

### 4. Update a Customer

```
PUT /api/customers/<id>
Content-Type: application/json
```

Supply only the fields you wish to modify (PATCH semantics):

```json
{ "phone": "555-0000", "address": "New Address, NY" }
```

**Response 200**

```json
{
  "status": "success",
  "data": {
    "id": 1,
    "name": "Alice Johnson",
    "email": "alice.johnson@example.com",
    "phone": "555-0000",
    "address": "New Address, NY",
    "created_at": "2024-01-15T10:00:00+00:00"
  }
}
```

**Response 400** — missing or non-JSON body  
**Response 404** — ID not found  
**Response 422** — duplicate email  

---

### 5. Delete a Customer

```
DELETE /api/customers/<id>
```

**Response 200**

```json
{ "status": "success", "message": "Customer 3 deleted." }
```

**Response 404**

```json
{ "status": "error", "message": "Customer 3 not found." }
```

---

## Error Envelope

All error responses follow this structure:

```json
{
  "status": "error",
  "message": "<human-readable description>"
}
```

| HTTP Status | Meaning                                    |
|-------------|--------------------------------------------|
| 200         | OK — request succeeded                     |
| 201         | Created — new resource created             |
| 400         | Bad Request — missing or invalid JSON body |
| 404         | Not Found — customer ID does not exist     |
| 422         | Unprocessable — validation / conflict error |

---

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Development server (SQLite file, auto-reloads)
python run.py

# Production (set env vars and use gunicorn)
DATABASE_URL=postgresql://user:pass@host/db FLASK_ENV=production gunicorn "app:create_app()"
```

---

## Running the Test Suite

```bash
# All tests
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Specific test file
pytest tests/test_customer_repository.py -v
pytest tests/test_customer_service.py -v
pytest tests/test_customer_routes.py -v
```

### Test layers

| File                           | Layer tested  | DB used             |
|--------------------------------|---------------|---------------------|
| `test_customer_repository.py`  | Repository    | In-memory SQLite    |
| `test_customer_service.py`     | Service       | Mock (no DB)        |
| `test_customer_routes.py`      | Routes (HTTP) | In-memory SQLite    |


---

## Data Model

| Field        | Type   | Description                          | Required on create |
|--------------|--------|--------------------------------------|--------------------|
| `id`         | int    | Auto-assigned unique identifier      | No (auto)          |
| `name`       | string | Full name of the customer            | **Yes**            |
| `email`      | string | Email address (unique, lower-cased)  | **Yes**            |
| `phone`      | string | Contact phone number                 | **Yes**            |
| `address`    | string | Physical address                     | **Yes**            |
| `created_at` | string | ISO-8601 UTC timestamp (auto-set)    | No (auto)          |

---

## Endpoints

### 1. List All Customers

```
GET /api/customers
```

**Response 200**

```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "id": 1,
      "name": "Alice Johnson",
      "email": "alice.johnson@example.com",
      "phone": "555-0101",
      "address": "123 Main St, New York, NY 10001",
      "created_at": "2024-01-15T10:00:00+00:00"
    }
  ]
}
```

---

### 2. Retrieve a Customer

```
GET /api/customers/<id>
```

**Response 200**

```json
{
  "status": "success",
  "data": {
    "id": 2,
    "name": "Bob Smith",
    "email": "bob.smith@example.com",
    "phone": "555-0102",
    "address": "456 Oak Ave, Los Angeles, CA 90001",
    "created_at": "2024-02-20T11:30:00+00:00"
  }
}
```

**Response 404**

```json
{
  "status": "error",
  "message": "Customer 99 not found."
}
```

---

### 3. Create a Customer

```
POST /api/customers
Content-Type: application/json
```

**Request body**

```json
{
  "name":    "Jane Doe",
  "email":   "jane.doe@example.com",
  "phone":   "555-9999",
  "address": "1 Example Lane, Austin, TX"
}
```

**Response 201**

```json
{
  "status": "success",
  "data": {
    "id": 6,
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "phone": "555-9999",
    "address": "1 Example Lane, Austin, TX",
    "created_at": "2026-05-07T09:00:00+00:00"
  }
}
```

**Response 400** — no JSON body or malformed JSON

```json
{ "status": "error", "message": "Request body must be valid JSON." }
```

**Response 422** — validation error (missing field or duplicate email)

```json
{ "status": "error", "message": "Missing required fields: ['email']" }
```

---

### 4. Update a Customer

```
PUT /api/customers/<id>
Content-Type: application/json
```

Supply only the fields you wish to modify (partial update):

```json
{ "phone": "555-0000", "address": "New Address, NY" }
```

**Response 200**

```json
{
  "status": "success",
  "data": { "id": 1, "name": "Alice Johnson", "phone": "555-0000", ... }
}
```

**Response 404** — ID not found  
**Response 422** — duplicate email  

---

### 5. Delete a Customer

```
DELETE /api/customers/<id>
```

**Response 200**

```json
{ "status": "success", "message": "Customer 3 deleted." }
```

**Response 404**

```json
{ "status": "error", "message": "Customer 99 not found." }
```

---

## Error Envelope

All error responses follow this structure:

```json
{
  "status": "error",
  "message": "<human-readable description>"
}
```

| HTTP Status | Meaning                                    |
|-------------|--------------------------------------------|
| 200         | OK — request succeeded                     |
| 201         | Created — new resource created             |
| 400         | Bad Request — missing or invalid JSON body |
| 404         | Not Found — customer ID does not exist     |
| 422         | Unprocessable — validation error           |

---

## Mock Data (Seed Records)

| ID | Name            | Email                         | Phone    |
|----|-----------------|-------------------------------|----------|
| 1  | Alice Johnson   | alice.johnson@example.com     | 555-0101 |
| 2  | Bob Smith       | bob.smith@example.com         | 555-0102 |
| 3  | Carol Williams  | carol.williams@example.com    | 555-0103 |
| 4  | David Brown     | david.brown@example.com       | 555-0104 |
| 5  | Eva Martinez    | eva.martinez@example.com      | 555-0105 |

The store resets to these five records each time the application starts.  
Tests reset the store via `mock_data.reset_store()`.

---

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Start the development server
python run.py
```

The API will be available at `http://127.0.0.1:5000`.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

| Test file                          | Coverage                          |
|------------------------------------|-----------------------------------|
| `tests/test_customer_service.py`   | Unit tests — service layer logic  |
| `tests/test_customer_routes.py`    | Integration tests — HTTP layer    |
