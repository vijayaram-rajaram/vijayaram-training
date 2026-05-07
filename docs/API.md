# Customer CRUD API — Documentation

## Overview

A RESTful API that manages **Customer** records using an in-memory mock data store.  
Base URL: `http://127.0.0.1:5000`

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
