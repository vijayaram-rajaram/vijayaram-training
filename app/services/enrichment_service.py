"""
app/services/enrichment_service.py
------------------------------------
Business-logic layer for customer-enrichment operations.

``EnrichmentService`` orchestrates calls to the third-party
``JSONPlaceholderClient`` and merges external data with the local
customer record.  It is intentionally decoupled from Flask so it can be
unit-tested without starting a server.  Both the customer service and
the external client can be injected for fully isolated tests.

Classes
-------
EnrichmentService
    Enrich a customer profile with third-party data.
"""

from __future__ import annotations

import logging
from typing import Any

from app.exceptions import CustomerNotFoundError, ExternalAPIError
from app.integrations.jsonplaceholder_client import JSONPlaceholderClient
from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Combines local customer data with third-party enrichment data.

    Dependency injection is used for both the customer service and the
    external API client so the class can be tested in isolation::

        from unittest.mock import MagicMock
        mock_client  = MagicMock(spec=JSONPlaceholderClient)
        mock_service = MagicMock(spec=CustomerService)
        svc = EnrichmentService(customer_service=mock_service,
                                client=mock_client)

    Args:
        customer_service (CustomerService | None): Local CRUD service.
            Defaults to a real ``CustomerService`` when ``None``.
        client (JSONPlaceholderClient | None): Third-party API client.
            Defaults to a real ``JSONPlaceholderClient`` when ``None``.
    """

    def __init__(
        self,
        customer_service: CustomerService | None = None,
        client: JSONPlaceholderClient | None = None,
    ) -> None:
        self._customer_svc: CustomerService = customer_service or CustomerService()
        self._client: JSONPlaceholderClient = client or JSONPlaceholderClient()

    # ------------------------------------------------------------------
    # Enrichment operations
    # ------------------------------------------------------------------

    def get_enriched_customer(self, customer_id: int) -> dict[str, Any]:
        """Return a customer record enriched with third-party profile data.

        The enrichment bundle includes the external user profile, a
        preview of recent posts, and a count of open to-do items.

        When the external API is unavailable the method returns the raw
        customer data with an ``enrichment_status`` field set to
        ``"unavailable"`` so the caller always gets a usable response.

        Args:
            customer_id (int): Internal customer primary key.

        Returns:
            dict: Combined payload::

                {
                    "customer": { ...local customer record... },
                    "enrichment": {
                        "external_user_id": 3,
                        "profile": { ... },
                        "recent_posts": [ {"id": 1, "title": "..."}, ... ],
                        "open_todos": 4,
                    },
                    "enrichment_status": "ok" | "unavailable"
                }

        Raises:
            CustomerNotFoundError: If *customer_id* does not exist
                locally (we do not attempt the external call in this case).
        """
        # Raises CustomerNotFoundError if the customer is absent.
        customer = self._customer_svc.get_by_id(customer_id)

        try:
            enrichment = self._client.get_enrichment_profile(customer_id)
            return {
                "customer": customer,
                "enrichment": enrichment,
                "enrichment_status": "ok",
            }
        except ExternalAPIError as exc:
            logger.warning(
                "Enrichment unavailable for customer %s: %s",
                customer_id,
                exc,
            )
            return {
                "customer": customer,
                "enrichment": None,
                "enrichment_status": "unavailable",
            }

    def get_posts_preview(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return a preview of recent posts from the enrichment API.

        Args:
            limit (int): Maximum number of posts to return.  Capped at
                100.  Defaults to 10.

        Returns:
            list[dict]: Post records with ``id``, ``userId``, and
                ``title`` fields.

        Raises:
            ExternalAPIError: If the remote API call fails.
        """
        limit = min(max(1, limit), 100)
        return self._client.get_posts(limit=limit)
