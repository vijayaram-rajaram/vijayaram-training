"""
tests/test_enrichment_routes.py
---------------------------------
Integration tests for the enrichment Blueprint routes.

Mock strategy
-------------
The module-level ``_service`` singleton in ``enrichment_routes`` is
replaced using ``unittest.mock.patch`` for every test that exercises a
service-level outcome.  This means:

  * No real database is accessed.
  * No real HTTP calls are made to JSONPlaceholder or any other API.
  * Each test controls *exactly* what ``EnrichmentService`` returns or
    raises, keeping tests fast and deterministic.

Pattern used::

    with patch("app.routes.enrichment_routes._service",
               spec=EnrichmentService) as mock_svc:
        # Configure the mock to return a specific payload …
        mock_svc.get_enriched_customer.return_value = {
            "customer": { ... },
            "enrichment": { ... },
            "enrichment_status": "ok"
        }
        # … or to raise a specific exception:
        mock_svc.get_posts_preview.side_effect = ExternalAPIRateLimitError(60)

        resp = client.get("/api/customers/1/enrich")
        # Assert HTTP status and response body.

Real 3rd-party response shapes being simulated
-----------------------------------------------
``GET /api/customers/1/enrich`` calls (internally):

    # 1. JSONPlaceholder user profile
    GET https://jsonplaceholder.typicode.com/users/1
    → { "id": 1, "name": "Leanne Graham", "email": "Sincere@april.biz",
        "address": {...}, "company": {...} }

    # 2. User posts
    GET https://jsonplaceholder.typicode.com/posts?userId=1
    → [ { "userId": 1, "id": 1, "title": "...", "body": "..." }, ... ]

    # 3. User todos
    GET https://jsonplaceholder.typicode.com/todos?userId=1
    → [ { "userId": 1, "id": 1, "title": "...", "completed": false }, ... ]

``GET /api/enrichment/posts?limit=5`` calls:

    GET https://jsonplaceholder.typicode.com/posts
    → [ { "userId": 1, "id": 1, "title": "...", "body": "..." },
        { "userId": 1, "id": 2, "title": "...", "body": "..." }, ... ]
    (first `limit` items are returned to the caller)

Coverage
--------
GET /api/customers/<id>/enrich
    * 200 with full enrichment payload.
    * 200 with ``enrichment_status: "unavailable"`` when the service
      returns a degraded result.
    * 404 when the customer does not exist.

GET /api/enrichment/posts
    * 200 with the default limit (10).
    * 200 with a custom ``?limit=N``.
    * 400 for non-integer or out-of-range limit values.
    * 429 when the service raises ``ExternalAPIRateLimitError``.
    * 503 when the service raises ``ExternalAPIUnavailableError``
      or ``ExternalAPITimeoutError``.
    * 502 for unexpected ``ExternalAPIError``.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import (
    CustomerNotFoundError,
    ExternalAPIError,
    ExternalAPIRateLimitError,
    ExternalAPITimeoutError,
    ExternalAPIUnavailableError,
)
from app.services.enrichment_service import EnrichmentService

# ---------------------------------------------------------------------------
# Fixture data — shapes mirror the real JSONPlaceholder API contract
# ---------------------------------------------------------------------------

# Local customer record as returned by CustomerService.get_by_id()
# Shape mirrors: GET /api/customers/1 → 200 { "status": "success", "data": {...} }
_CUSTOMER = {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com",
    "phone": "555-0001",
    "address": "1 Main St",
    "created_at": "2024-01-01T00:00:00+00:00",
}

# Enrichment bundle produced by JSONPlaceholderClient.get_enrichment_profile()
# Built from three upstream calls:
#   GET https://jsonplaceholder.typicode.com/users/1
#     → external_user_id + profile dict
#   GET https://jsonplaceholder.typicode.com/posts?userId=1
#     → recent_posts (first 5 titles)
#   GET https://jsonplaceholder.typicode.com/todos?userId=1
#     → open_todos (count of completed=false items)
_ENRICHMENT = {
    "external_user_id": 1,
    "profile": {"id": 1, "name": "Leanne Graham"},
    "recent_posts": [{"id": 1, "title": "Post A"}],
    "open_todos": 3,
}

# Full response shape for GET /api/customers/1/enrich → enrichment available
# Wraps _CUSTOMER + _ENRICHMENT with enrichment_status="ok"
_ENRICH_RESPONSE_OK = {
    "customer": _CUSTOMER,
    "enrichment": _ENRICHMENT,
    "enrichment_status": "ok",
}

# Full response shape for GET /api/customers/1/enrich → external API is down
# enrichment=null, enrichment_status="unavailable", customer is always present
_ENRICH_RESPONSE_UNAVAILABLE = {
    "customer": _CUSTOMER,
    "enrichment": None,
    "enrichment_status": "unavailable",
}

# Posts list as returned by JSONPlaceholderClient.get_posts(limit=10)
# Shape mirrors: GET https://jsonplaceholder.typicode.com/posts
#   → [{"userId": 1, "id": 1, "title": "...", "body": "..."}, ...]
_POSTS = [{"userId": 1, "id": i, "title": f"Post {i}"} for i in range(1, 11)]


# ---------------------------------------------------------------------------
# GET /api/customers/<id>/enrich
# ---------------------------------------------------------------------------


class TestEnrichCustomerRoute:
    def test_200_with_enrichment(self, client):
        # Mock: EnrichmentService.get_enriched_customer(1) returns full bundle.
        # Simulates all three upstream calls succeeding:
        #   GET /users/1 → 200, GET /posts?userId=1 → 200, GET /todos?userId=1 → 200
        # Expected API response: 200 { "status": "success", "data": { ..., "enrichment_status": "ok" } }
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_enriched_customer.return_value = _ENRICH_RESPONSE_OK
            resp = client.get("/api/customers/1/enrich")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["data"]["enrichment_status"] == "ok"
        assert body["data"]["customer"]["email"] == "alice@example.com"

    def test_200_degraded_when_enrichment_unavailable(self, client):
        # Mock: EnrichmentService.get_enriched_customer(1) returns degraded bundle.
        # Simulates the upstream JSONPlaceholder call failing (timeout / 5xx).
        # Expected API response: still 200, enrichment=null, enrichment_status="unavailable"
        # The customer is always included so the caller is never fully blocked.
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_enriched_customer.return_value = _ENRICH_RESPONSE_UNAVAILABLE
            resp = client.get("/api/customers/1/enrich")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["enrichment_status"] == "unavailable"
        assert body["data"]["enrichment"] is None

    def test_404_when_customer_not_found(self, client):
        # Mock: EnrichmentService.get_enriched_customer(99) raises CustomerNotFoundError.
        # Simulates requesting a customer ID that does not exist locally.
        # No upstream call to JSONPlaceholder is made in this case.
        # Expected API response: 404 { "status": "error", "message": "Customer 99 not found." }
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_enriched_customer.side_effect = CustomerNotFoundError(99)
            resp = client.get("/api/customers/99/enrich")

        assert resp.status_code == 404
        body = resp.get_json()
        assert body["status"] == "error"
        assert "99" in body["message"]


# ---------------------------------------------------------------------------
# GET /api/enrichment/posts
# ---------------------------------------------------------------------------


class TestListPostsRoute:
    def test_200_default_limit(self, client):
        # Mock: EnrichmentService.get_posts_preview(limit=10) returns 10 posts.
        # Simulates: GET https://jsonplaceholder.typicode.com/posts (first 10 items)
        # Expected API response: 200 { "status": "success", "count": 10, "data": [...] }
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_posts_preview.return_value = _POSTS
            resp = client.get("/api/enrichment/posts")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["count"] == len(_POSTS)
        mock_svc.get_posts_preview.assert_called_once_with(limit=10)

    def test_200_custom_limit(self, client):
        # Mock: EnrichmentService.get_posts_preview(limit=5) returns 5 posts.
        # Verifies the ?limit= query parameter is parsed and forwarded correctly.
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_posts_preview.return_value = _POSTS[:5]
            resp = client.get("/api/enrichment/posts?limit=5")

        assert resp.status_code == 200
        mock_svc.get_posts_preview.assert_called_once_with(limit=5)

    @pytest.mark.parametrize("bad_limit", ["abc", "0", "101", "-1", ""])
    def test_400_invalid_limit(self, client, bad_limit):
        # No mock needed — validation happens before any service call is made.
        # Expected API response: 400 { "status": "error", "message": "'limit' must be..." }
        resp = client.get(f"/api/enrichment/posts?limit={bad_limit}")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["status"] == "error"
        assert "limit" in body["message"].lower()

    def test_429_on_rate_limit_error(self, client):
        # Mock: EnrichmentService.get_posts_preview raises ExternalAPIRateLimitError.
        # Simulates: GET https://jsonplaceholder.typicode.com/posts → 429
        #            with Retry-After: 60
        # Expected API response: 429 { "status": "error", "message": "..." }
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_posts_preview.side_effect = ExternalAPIRateLimitError(60)
            resp = client.get("/api/enrichment/posts")

        assert resp.status_code == 429
        assert resp.get_json()["status"] == "error"

    def test_503_on_unavailable_error(self, client):
        # Mock: EnrichmentService.get_posts_preview raises ExternalAPIUnavailableError.
        # Simulates: GET https://jsonplaceholder.typicode.com/posts → 503 (all retries exhausted)
        # Expected API response: 503 { "status": "error", "message": "Enrichment service temporarily unavailable." }
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_posts_preview.side_effect = ExternalAPIUnavailableError(503)
            resp = client.get("/api/enrichment/posts")

        assert resp.status_code == 503

    def test_503_on_timeout_error(self, client):
        # Mock: EnrichmentService.get_posts_preview raises ExternalAPITimeoutError.
        # Simulates: GET https://jsonplaceholder.typicode.com/posts times out
        #            (provider exceeds ENRICHMENT_API_TIMEOUT seconds).
        # Expected API response: 503 { "status": "error", "message": "Enrichment service temporarily unavailable." }
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_posts_preview.side_effect = ExternalAPITimeoutError(
                "https://example.com"
            )
            resp = client.get("/api/enrichment/posts")

        assert resp.status_code == 503

    def test_502_on_generic_api_error(self, client):
        # Mock: EnrichmentService.get_posts_preview raises a generic ExternalAPIError.
        # Simulates: Provider returned an unexpected 4xx (e.g. 400 Bad Request).
        # Expected API response: 502 { "status": "error", "message": "An error occurred..." }
        # Internal error details are never forwarded to the caller.
        with patch(
            "app.routes.enrichment_routes._service",
            spec=EnrichmentService,
        ) as mock_svc:
            mock_svc.get_posts_preview.side_effect = ExternalAPIError("unexpected")
            resp = client.get("/api/enrichment/posts")

        assert resp.status_code == 502
