"""
tests/test_enrichment_service.py
----------------------------------
Unit tests for ``app.services.enrichment_service.EnrichmentService``.

Mock strategy
-------------
Both collaborators are replaced with ``MagicMock`` instances so the
service logic is tested in complete isolation — no database, no HTTP
client, no real Flask application context is needed.

``CustomerService`` mock contract::

    mock_customer_svc.get_by_id(customer_id: int) → dict
    # Returns a customer dict or raises CustomerNotFoundError.
    # Simulates local DB lookup.
    #
    # Example return value:
    {
        "id": 1, "name": "Alice", "email": "alice@example.com",
        "phone": "555-0001", "address": "1 Main St",
        "created_at": "2024-01-01T00:00:00+00:00"
    }

``JSONPlaceholderClient`` mock contract::

    mock_client.get_enrichment_profile(customer_id: int) → dict
    # Simulates a successful third-party API response bundle.
    # Real API: GET https://jsonplaceholder.typicode.com/users/{id}
    #           GET https://jsonplaceholder.typicode.com/posts?userId={id}
    #           GET https://jsonplaceholder.typicode.com/todos?userId={id}
    #
    # Example return value:
    {
        "external_user_id": 1,
        "profile": {
            "id": 1,
            "name": "Leanne Graham",
            "email": "Sincere@april.biz",
            "company": { "name": "Romaguera-Crona" }
        },
        "recent_posts": [
            { "id": 1, "title": "sunt aut facere repellat provident" },
            { "id": 2, "title": "qui est esse" }
        ],
        "open_todos": 3
    }
    # Or raises an ExternalAPIError subclass to simulate provider failure.

Coverage
--------
* ``get_enriched_customer`` returns merged data on success.
* ``get_enriched_customer`` falls back gracefully when the external API
  raises any ``ExternalAPIError``.
* ``get_enriched_customer`` re-raises ``CustomerNotFoundError`` so the
  route layer can return 404.
* ``get_posts_preview`` delegates to the client and applies the limit.
* ``get_posts_preview`` clamps the limit to [1, 100].
"""

import pytest
from unittest.mock import MagicMock

from app.exceptions import (
    CustomerNotFoundError,
    ExternalAPIError,
    ExternalAPITimeoutError,
    ExternalAPIUnavailableError,
)
from app.integrations.jsonplaceholder_client import JSONPlaceholderClient
from app.services.customer_service import CustomerService
from app.services.enrichment_service import EnrichmentService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CUSTOMER = {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com",
    "phone": "555-0001",
    "address": "1 Main St",
    "created_at": "2024-01-01T00:00:00+00:00",
}

_ENRICHMENT = {
    "external_user_id": 1,
    "profile": {"id": 1, "name": "Leanne Graham"},
    "recent_posts": [{"id": 1, "title": "Post A"}],
    "open_todos": 3,
}


def _make_service(
    customer_result=_CUSTOMER,
    enrichment_result=_ENRICHMENT,
    customer_side_effect=None,
    enrichment_side_effect=None,
) -> EnrichmentService:
    mock_customer_svc = MagicMock(spec=CustomerService)
    mock_client = MagicMock(spec=JSONPlaceholderClient)

    if customer_side_effect:
        mock_customer_svc.get_by_id.side_effect = customer_side_effect
    else:
        mock_customer_svc.get_by_id.return_value = customer_result

    if enrichment_side_effect:
        mock_client.get_enrichment_profile.side_effect = enrichment_side_effect
    else:
        mock_client.get_enrichment_profile.return_value = enrichment_result

    return EnrichmentService(customer_service=mock_customer_svc, client=mock_client)


# ---------------------------------------------------------------------------
# get_enriched_customer – success
# ---------------------------------------------------------------------------


class TestGetEnrichedCustomerSuccess:
    def test_returns_merged_payload(self):
        svc = _make_service()
        result = svc.get_enriched_customer(1)
        assert result["customer"] == _CUSTOMER
        assert result["enrichment"] == _ENRICHMENT
        assert result["enrichment_status"] == "ok"

    def test_passes_customer_id_to_enrichment_client(self):
        mock_client = MagicMock(spec=JSONPlaceholderClient)
        mock_client.get_enrichment_profile.return_value = _ENRICHMENT
        mock_svc = MagicMock(spec=CustomerService)
        mock_svc.get_by_id.return_value = _CUSTOMER
        svc = EnrichmentService(customer_service=mock_svc, client=mock_client)
        svc.get_enriched_customer(7)
        mock_client.get_enrichment_profile.assert_called_once_with(7)


# ---------------------------------------------------------------------------
# get_enriched_customer – external API failures (graceful degradation)
# ---------------------------------------------------------------------------


class TestGetEnrichedCustomerFallback:
    @pytest.mark.parametrize(
        "exc",
        [
            ExternalAPIError("boom"),
            ExternalAPITimeoutError("https://example.com"),
            ExternalAPIUnavailableError(503),
        ],
    )
    def test_returns_unavailable_status_on_api_error(self, exc):
        svc = _make_service(enrichment_side_effect=exc)
        result = svc.get_enriched_customer(1)
        assert result["enrichment"] is None
        assert result["enrichment_status"] == "unavailable"
        assert result["customer"] == _CUSTOMER

    def test_customer_data_always_present_on_api_error(self):
        svc = _make_service(enrichment_side_effect=ExternalAPIError("down"))
        result = svc.get_enriched_customer(1)
        assert result["customer"]["email"] == "alice@example.com"


# ---------------------------------------------------------------------------
# get_enriched_customer – customer not found
# ---------------------------------------------------------------------------


class TestGetEnrichedCustomerNotFound:
    def test_raises_customer_not_found_error(self):
        svc = _make_service(customer_side_effect=CustomerNotFoundError(99))
        with pytest.raises(CustomerNotFoundError):
            svc.get_enriched_customer(99)

    def test_does_not_call_external_api_when_customer_missing(self):
        mock_client = MagicMock(spec=JSONPlaceholderClient)
        mock_svc = MagicMock(spec=CustomerService)
        mock_svc.get_by_id.side_effect = CustomerNotFoundError(99)
        svc = EnrichmentService(customer_service=mock_svc, client=mock_client)
        with pytest.raises(CustomerNotFoundError):
            svc.get_enriched_customer(99)
        mock_client.get_enrichment_profile.assert_not_called()


# ---------------------------------------------------------------------------
# get_posts_preview
# ---------------------------------------------------------------------------


class TestGetPostsPreview:
    def test_delegates_limit_to_client(self):
        mock_client = MagicMock(spec=JSONPlaceholderClient)
        mock_client.get_posts.return_value = [{"id": i} for i in range(5)]
        svc = EnrichmentService(customer_service=MagicMock(), client=mock_client)
        svc.get_posts_preview(limit=5)
        mock_client.get_posts.assert_called_once_with(limit=5)

    def test_default_limit_is_10(self):
        mock_client = MagicMock(spec=JSONPlaceholderClient)
        mock_client.get_posts.return_value = []
        svc = EnrichmentService(customer_service=MagicMock(), client=mock_client)
        svc.get_posts_preview()
        mock_client.get_posts.assert_called_once_with(limit=10)

    @pytest.mark.parametrize(
        "requested, expected",
        [
            (0, 1),     # below minimum → clamped to 1
            (-5, 1),    # negative → clamped to 1
            (101, 100), # above maximum → clamped to 100
            (200, 100), # far above maximum → clamped to 100
        ],
    )
    def test_limit_clamped(self, requested, expected):
        mock_client = MagicMock(spec=JSONPlaceholderClient)
        mock_client.get_posts.return_value = []
        svc = EnrichmentService(customer_service=MagicMock(), client=mock_client)
        svc.get_posts_preview(limit=requested)
        mock_client.get_posts.assert_called_once_with(limit=expected)
