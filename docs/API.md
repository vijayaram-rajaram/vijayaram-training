# Customer CRUD API — Documentation

## Overview

A RESTful API that manages **Customer** records backed by a **SQLite** database
(switchable to PostgreSQL or MySQL via the `DATABASE_URL` environment variable).

The API also integrates with a third-party enrichment service
([JSONPlaceholder](https://jsonplaceholder.typicode.com)) to augment customer
records with external profile data, recent activity, and to-do summaries.

```
Base URL: http://127.0.0.1:5000
```

---

## Architecture

```
┌─────────────┐     HTTP      ┌───────────────────────┐
│   Client    │──────────────▶│     Route layer        │  app/routes/
└─────────────┘               │  (Flask Blueprints)    │
                               └──────────┬────────────┘
                                          │ calls
                         ┌────────────────┼──────────────────┐
                         │                │                  │
               ┌─────────▼──────┐  ┌──────▼───────────────┐ │
               │ CustomerService│  │  EnrichmentService   │ │
               │ (CRUD rules)   │  │  (merge + fallback)  │ │
               └─────────┬──────┘  └──────┬───────────────┘ │
                         │                │                  │
               ┌─────────▼──────┐  ┌──────▼──────────────┐  │
               │  Repository    │  │ JSONPlaceholderClient│  │
               │  (DB access)   │  │  (BaseHTTPClient)    │  │
               └─────────┬──────┘  └──────┬───────────────┘  │
                         │ SQLAlchemy      │ HTTPS / retries   │
               ┌─────────▼──────┐  ┌──────▼──────────────┐   │
               │   Database     │  │  3rd-party API       │   │
               │SQLite/Postgres │  │ jsonplaceholder.typi │   │
               └────────────────┘  │    code.typicode.com │   │
                                   └─────────────────────┘   │
```

### Layer responsibilities

| Layer              | Module                            | Responsibility                                        |
|--------------------|-----------------------------------|-------------------------------------------------------|
| Routes             | `app/routes/customer_routes`      | HTTP routing, request parsing, response envelope      |
| Routes             | `app/routes/enrichment_routes`    | Enrichment endpoints, error → HTTP status mapping     |
| Service            | `app/services/customer_service`   | CRUD business rules, validation, domain exceptions    |
| Service            | `app/services/enrichment_service` | Merge local + external data; graceful degradation     |
| Repository         | `app/repositories/customer_repo`  | All SQLAlchemy queries, commit / rollback             |
| HTTP Client        | `app/integrations/http_client`    | Retry, timeout, API-key injection, error mapping      |
| API Client         | `app/integrations/jsonplaceholder_client` | JSONPlaceholder-specific endpoint wrappers    |
| Model              | `app/models/customer`             | ORM mapping, `to_dict` serialisation                 |
| Config             | `app/config`                      | Environment-based configuration                       |
| Exceptions         | `app/exceptions`                  | Typed domain exceptions (CRUD + integration)          |

---

## Configuration

### Application

| Environment key | Default                      | Notes                                    |
|-----------------|------------------------------|------------------------------------------|
| `DATABASE_URL`  | `sqlite:///customers_dev.db` | Any SQLAlchemy-compatible URI            |
| `FLASK_ENV`     | `development`                | `development` · `testing` · `production` |
| `SECRET_KEY`    | `dev-secret-…`               | **Override in production**               |

### Third-party integration

| Environment key             | Default                                    | Notes                                           |
|-----------------------------|--------------------------------------------|-------------------------------------------------|
| `ENRICHMENT_API_BASE_URL`   | `https://jsonplaceholder.typicode.com`     | Swap to a real provider without code changes    |
| `ENRICHMENT_API_KEY`        | _(unset)_                                  | Bearer token; leave blank for public sandboxes  |
| `ENRICHMENT_API_TIMEOUT`    | `10`                                       | Per-request timeout in seconds                  |
| `ENRICHMENT_API_MAX_RETRIES`| `3`                                        | Retry attempts on 5xx / network errors          |
| `ENRICHMENT_API_BACKOFF`    | `0.5`                                      | Exponential back-off multiplier (seconds)       |

---

## Security Considerations

### API key management

- API keys and tokens are **never hardcoded**. All secrets are read from
  environment variables at startup (see table above).
- The `Authorization: Bearer <token>` header is injected by `BaseHTTPClient`
  and is never logged or included in exception messages.
- In production, set `ENRICHMENT_API_KEY` via your secrets manager (e.g.
  AWS Secrets Manager, HashiCorp Vault, Azure Key Vault) or a `.env` file that
  is excluded from source control (`.gitignore`).

### Secret scrubbing in logs

`BaseHTTPClient._safe_url()` redacts any query-string parameter whose name
matches `api_key`, `token`, `secret`, `password`, or `access_token` before the
URL appears in log output or exception messages:

```
# Raw URL (never logged):
https://api.example.com/data?api_key=supersecret&page=1

# Safe URL (logged / in error messages):
https://api.example.com/data?api_key=[REDACTED]&page=1
```

### Transport security

- All outbound calls use HTTPS. The `requests` session mounts retry adapters
  for both `https://` and `http://` but production endpoints must use TLS.
- Certificate verification is left at the `requests` default (enabled). Do
  not disable it in production.

### Error surface

- Internal URLs, stack traces, and provider error messages are **never
  forwarded** to API consumers.  Route handlers catch integration exceptions
  and return generic, safe messages (e.g. `"Enrichment service temporarily
  unavailable."`).

---

## Retry and Timeout Behaviour

```
Request ──► BaseHTTPClient._request()
                │
                ├─ ConnectionError / Timeout
                │       └─► raise immediately (no retry)
                │
                ├─ HTTP 429 (rate limit)
                │       └─► raise ExternalAPIRateLimitError immediately
                │           (never retried – would amplify load)
                │
                ├─ HTTP 5xx (server error)
                │       └─► tenacity retries up to ENRICHMENT_API_MAX_RETRIES
                │           with exponential back-off:
                │           wait = BACKOFF × 2^(attempt − 1)  (max 30 s)
                │           If all attempts fail → ExternalAPIUnavailableError
                │
                └─ HTTP 4xx (non-429)
                        └─► raise ExternalAPIError immediately
```

| Exception                   | Trigger                        | HTTP response |
|-----------------------------|--------------------------------|---------------|
| `ExternalAPITimeoutError`   | Request timed out              | 503           |
| `ExternalAPIRateLimitError` | Remote returned 429            | 429           |
| `ExternalAPIUnavailableError`| Remote returned 5xx (all retries exhausted) | 503 |
| `ExternalAPIError`          | Remote returned other 4xx      | 502           |

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

## Enrichment Endpoints

These endpoints integrate with the third-party
[JSONPlaceholder](https://jsonplaceholder.typicode.com) API to augment
customer data with external profile information, recent posts, and open
to-do counts.  No authentication is required for the sandbox; swap in a
real provider by changing `ENRICHMENT_API_BASE_URL` and
`ENRICHMENT_API_KEY` environment variables.

---

### 6. Get Enriched Customer Profile

```
GET /api/customers/<id>/enrich
```

Fetches the local customer record and enriches it with data from the
third-party API.  If the external API is unavailable the endpoint still
returns **200** with the local customer data and
`"enrichment_status": "unavailable"` so callers are never blocked.

**Response 200 — enrichment available**

```json
{
  "status": "success",
  "data": {
    "customer": {
      "id": 1,
      "name": "Alice Johnson",
      "email": "alice.johnson@example.com",
      "phone": "555-0101",
      "address": "123 Main St, New York, NY 10001",
      "created_at": "2024-01-15T10:00:00+00:00"
    },
    "enrichment": {
      "external_user_id": 1,
      "profile": {
        "id": 1,
        "name": "Leanne Graham",
        "username": "Bret",
        "email": "Sincere@april.biz",
        "address": {
          "street": "Kulas Light",
          "suite": "Apt. 556",
          "city": "Gwenborough",
          "zipcode": "92998-3874",
          "geo": { "lat": "-37.3159", "lng": "81.1496" }
        },
        "phone": "1-770-736-8031 x56442",
        "website": "hildegard.org",
        "company": {
          "name": "Romaguera-Crona",
          "catchPhrase": "Multi-layered client-server neural-net",
          "bs": "harness real-time e-markets"
        }
      },
      "recent_posts": [
        { "id": 1, "title": "sunt aut facere repellat provident" },
        { "id": 2, "title": "qui est esse" },
        { "id": 3, "title": "ea molestias quasi exercitationem" }
      ],
      "open_todos": 4
    },
    "enrichment_status": "ok"
  }
}
```

**Response 200 — external API unavailable (graceful degradation)**

```json
{
  "status": "success",
  "data": {
    "customer": {
      "id": 1,
      "name": "Alice Johnson",
      "email": "alice.johnson@example.com",
      "phone": "555-0101",
      "address": "123 Main St, New York, NY 10001",
      "created_at": "2024-01-15T10:00:00+00:00"
    },
    "enrichment": null,
    "enrichment_status": "unavailable"
  }
}
```

**Response 404** — customer ID not found

```json
{ "status": "error", "message": "Customer 99 not found." }
```

---

### 7. List Posts Preview

```
GET /api/enrichment/posts?limit=N
```

Fetches recent posts from the enrichment API.  Useful for activity feeds
or content-discovery features.

**Query parameters**

| Parameter | Type    | Default | Range  | Description                        |
|-----------|---------|---------|--------|------------------------------------|
| `limit`   | integer | `10`    | 1–100  | Maximum number of posts to return  |

**Request examples**

```
GET /api/enrichment/posts
GET /api/enrichment/posts?limit=5
```

**Response 200**

```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "userId": 1,
      "id": 1,
      "title": "sunt aut facere repellat provident occaecati",
      "body": "quia et suscipit\nsuscipit recusandae..."
    },
    {
      "userId": 1,
      "id": 2,
      "title": "qui est esse",
      "body": "est rerum tempore vitae..."
    }
  ]
}
```

**Response 400** — `limit` is not an integer or is out of range

```json
{ "status": "error", "message": "'limit' must be an integer between 1 and 100." }
```

**Response 429** — enrichment API rate-limited this server

```json
{ "status": "error", "message": "External API rate limit exceeded. Retry after 60s." }
```

**Response 503** — enrichment API timed out or returned a 5xx error

```json
{ "status": "error", "message": "Enrichment service temporarily unavailable." }
```

**Response 502** — unexpected error from the enrichment API

```json
{ "status": "error", "message": "An error occurred while fetching enrichment data." }
```

---

## Upstream API Contract (JSONPlaceholder)

This section documents every HTTP request our service makes **to** the
third-party provider and the exact response shape it expects.  These
contracts are what the mocks in the test suite reproduce.

Base URL (configurable via `ENRICHMENT_API_BASE_URL`):
```
https://jsonplaceholder.typicode.com
```

---

### U1 · Get User Profile

Used by `JSONPlaceholderClient.get_user(user_id)` inside
`get_enrichment_profile()`.

**Outbound request**

```
GET /users/{user_id}
Accept: application/json
Authorization: Bearer <ENRICHMENT_API_KEY>   # omitted when key is unset
```

**Expected response — 200 OK**

```json
{
  "id": 1,
  "name": "Leanne Graham",
  "username": "Bret",
  "email": "Sincere@april.biz",
  "address": {
    "street": "Kulas Light",
    "suite": "Apt. 556",
    "city": "Gwenborough",
    "zipcode": "92998-3874",
    "geo": { "lat": "-37.3159", "lng": "81.1496" }
  },
  "phone": "1-770-736-8031 x56442",
  "website": "hildegard.org",
  "company": {
    "name": "Romaguera-Crona",
    "catchPhrase": "Multi-layered client-server neural-net",
    "bs": "harness real-time e-markets"
  }
}
```

**Fields used by the service**

| Field     | Used as                              |
|-----------|--------------------------------------|
| `id`      | `enrichment.profile.id`              |
| `name`    | `enrichment.profile.name`            |
| `email`   | `enrichment.profile.email`           |
| `address` | `enrichment.profile.address`         |
| `company` | `enrichment.profile.company`         |

---

### U2 · Get User Posts

Used by `JSONPlaceholderClient.get_posts_by_user(user_id)` inside
`get_enrichment_profile()`.

**Outbound request**

```
GET /posts?userId={user_id}
Accept: application/json
Authorization: Bearer <ENRICHMENT_API_KEY>   # omitted when key is unset
```

**Expected response — 200 OK**

```json
[
  {
    "userId": 1,
    "id": 1,
    "title": "sunt aut facere repellat provident occaecati excepturi optio",
    "body": "quia et suscipit\nsuscipit recusandae consequuntur..."
  },
  {
    "userId": 1,
    "id": 2,
    "title": "qui est esse",
    "body": "est rerum tempore vitae..."
  }
]
```

**Fields used by the service**

Only the first 5 items are kept.  For each item, only `id` and `title`
are surfaced in `enrichment.recent_posts`.

---

### U3 · Get User Todos

Used by `JSONPlaceholderClient.get_todos_by_user(user_id)` inside
`get_enrichment_profile()`.

**Outbound request**

```
GET /todos?userId={user_id}
Accept: application/json
Authorization: Bearer <ENRICHMENT_API_KEY>   # omitted when key is unset
```

**Expected response — 200 OK**

```json
[
  { "userId": 1, "id": 1, "title": "delectus aut autem",          "completed": false },
  { "userId": 1, "id": 2, "title": "quis ut nam facilis et officia", "completed": false },
  { "userId": 1, "id": 3, "title": "fugiat veniam minus",           "completed": false },
  { "userId": 1, "id": 4, "title": "et porro tempora",              "completed": true  }
]
```

**Fields used by the service**

`completed=false` items are counted to produce `enrichment.open_todos`.

---

### U4 · Get All Posts (preview list)

Used by `JSONPlaceholderClient.get_posts(limit)` inside
`EnrichmentService.get_posts_preview()`.

**Outbound request**

```
GET /posts
Accept: application/json
Authorization: Bearer <ENRICHMENT_API_KEY>   # omitted when key is unset
```

**Expected response — 200 OK**

```json
[
  { "userId": 1, "id": 1,  "title": "sunt aut facere...", "body": "quia et suscipit..." },
  { "userId": 1, "id": 2,  "title": "qui est esse",       "body": "est rerum tempore..." },
  { "userId": 2, "id": 11, "title": "et ea vero...",      "body": "delectus rerum..." }
]
```

The service returns only the first `limit` items (default: 10, max: 100).
The full `body` field is forwarded unchanged.

---

### Customer-ID to External-User-ID mapping

JSONPlaceholder provides exactly 10 users (IDs 1–10).  Internal customer
IDs are mapped deterministically:

```
external_user_id = (customer_id % 10) or 10
```

| customer_id | external_user_id |
|-------------|-----------------|
| 1           | 1               |
| 10          | 10              |
| 11          | 1               |
| 25          | 5               |

This mapping is stable (same customer always maps to the same external
profile) and can be replaced when integrating a real provider that
accepts your actual customer identifiers.

---

## Error Envelope

All responses (CRUD and enrichment) use the same envelope:

```json
{
  "status": "success" | "error",
  "data":    <payload>,           // present on success
  "count":   <integer>,           // present on list responses
  "message": "<description>"      // present on error
}
```

### CRUD status codes

| HTTP Status | Meaning                                    |
|-------------|--------------------------------------------|
| 200         | OK — request succeeded                     |
| 201         | Created — new resource created             |
| 400         | Bad Request — missing or invalid JSON body |
| 404         | Not Found — customer ID does not exist     |
| 422         | Unprocessable — validation / conflict error|

### Integration status codes

| HTTP Status | Trigger                                               |
|-------------|-------------------------------------------------------|
| 200         | Enrichment OK or gracefully degraded                  |
| 400         | Invalid query parameter                               |
| 404         | Customer not found (external call never attempted)    |
| 429         | Remote enrichment API rate-limited this server        |
| 502         | Unexpected 4xx from remote API                        |
| 503         | Remote API timed out or returned 5xx (all retries exhausted) |

---

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Development server (SQLite file, auto-reloads)
python run.py

# Production (set env vars and use gunicorn)
DATABASE_URL=postgresql://user:pass@host/db \
FLASK_ENV=production \
ENRICHMENT_API_KEY=<your-key> \
gunicorn "app:create_app()"
```

---

## Running the Test Suite

```bash
# All tests
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Integration-only
pytest tests/test_enrichment_routes.py tests/test_enrichment_service.py tests/test_http_client.py -v
```

### Test layers

| File                             | Layer tested          | Isolation technique                              |
|----------------------------------|-----------------------|--------------------------------------------------|
| `test_customer_repository.py`    | Repository            | In-memory SQLite per test                        |
| `test_customer_service.py`       | Service               | `MagicMock(spec=CustomerRepository)`             |
| `test_customer_routes.py`        | Routes (HTTP / CRUD)  | In-memory SQLite per test                        |
| `test_http_client.py`            | HTTP client           | `responses` library intercepts all `requests` calls |
| `test_enrichment_service.py`     | Enrichment service    | `MagicMock(spec=CustomerService)` + `MagicMock(spec=JSONPlaceholderClient)` |
| `test_enrichment_routes.py`      | Enrichment routes     | `unittest.mock.patch` on `_service` module-level singleton |

### Mock strategy for external API calls

**`test_http_client.py`** — uses the [`responses`](https://github.com/getsentry/responses)
library to register fake HTTP responses at the transport layer.  No real
network sockets are opened:

```python
import responses as rsps_lib

@rsps_lib.activate                          # intercepts all requests.* calls
def test_get_returns_json_dict(self):
    # Register the fake remote response
    rsps_lib.add(
        rsps_lib.GET,
        "https://test.example.com/users/1",
        json={"id": 1, "name": "Alice"},    # simulated API payload
        status=200,
    )
    client = BaseHTTPClient(base_url="https://test.example.com", ...)
    result = client.get("/users/1")
    assert result == {"id": 1, "name": "Alice"}
```

**`test_enrichment_service.py`** — replaces `JSONPlaceholderClient` with a
`MagicMock` so no HTTP client is created at all:

```python
mock_client = MagicMock(spec=JSONPlaceholderClient)
mock_client.get_enrichment_profile.return_value = {
    "external_user_id": 1,
    "profile": {"id": 1, "name": "Leanne Graham"},
    "recent_posts": [{"id": 1, "title": "Post A"}],
    "open_todos": 3,
}
svc = EnrichmentService(customer_service=mock_svc, client=mock_client)
```

**`test_enrichment_routes.py`** — patches the module-level `_service`
singleton in the route module so no real service or client is created:

```python
with patch("app.routes.enrichment_routes._service", spec=EnrichmentService) as mock_svc:
    mock_svc.get_enriched_customer.return_value = { ... }
    resp = client.get("/api/customers/1/enrich")
```

