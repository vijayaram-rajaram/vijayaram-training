"""
app/routes/enrichment_routes.py
---------------------------------
Flask Blueprint for third-party enrichment endpoints.

All endpoints are read-only (GET) and delegate business logic to
``EnrichmentService``.  External API errors are caught and translated
into appropriate HTTP responses – the raw exception detail (which may
contain internal URLs or partial tokens) is never exposed to clients.

Endpoints
---------
GET /api/customers/<id>/enrich
    Return the customer record enriched with third-party profile data.
    Falls back gracefully when the external API is unavailable.

GET /api/enrichment/posts
    Return a preview of recent posts from the enrichment API.
    Accepts an optional ``?limit=N`` query parameter (1–100, default 10).

All responses follow the same envelope used throughout this project::

    {
        "status": "success" | "error",
        "data":   <payload>,          # present on success
        "message": "<description>"    # present on error
    }
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from app.exceptions import (
    CustomerNotFoundError,
    ExternalAPIError,
    ExternalAPIRateLimitError,
    ExternalAPITimeoutError,
    ExternalAPIUnavailableError,
)
from app.services.enrichment_service import EnrichmentService

logger = logging.getLogger(__name__)

enrichment_bp = Blueprint("enrichment", __name__)

_service = EnrichmentService()


# ---------------------------------------------------------------------------
# GET /api/customers/<id>/enrich
# ---------------------------------------------------------------------------


@enrichment_bp.route("/api/customers/<int:customer_id>/enrich", methods=["GET"])
def enrich_customer(customer_id: int):
    """Return an enriched customer profile.

    **GET /api/customers/<customer_id>/enrich**

    Response 200 (enrichment available)::

        {
            "status": "success",
            "data": {
                "customer": { ...local customer fields... },
                "enrichment": {
                    "external_user_id": 3,
                    "profile": { "name": "...", "email": "...", "company": {...} },
                    "recent_posts": [ {"id": 1, "title": "..."}, ... ],
                    "open_todos": 4
                },
                "enrichment_status": "ok"
            }
        }

    Response 200 (enrichment unavailable – external API down)::

        {
            "status": "success",
            "data": {
                "customer": { ...local customer fields... },
                "enrichment": null,
                "enrichment_status": "unavailable"
            }
        }

    Response 404::

        { "status": "error", "message": "Customer 99 not found." }
    """
    try:
        data = _service.get_enriched_customer(customer_id)
    except CustomerNotFoundError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 404
    return jsonify({"status": "success", "data": data}), 200


# ---------------------------------------------------------------------------
# GET /api/enrichment/posts
# ---------------------------------------------------------------------------


@enrichment_bp.route("/api/enrichment/posts", methods=["GET"])
def list_posts():
    """Return a preview of posts from the enrichment API.

    **GET /api/enrichment/posts?limit=N**

    Query parameters:
        limit (int): Number of posts to return (1–100, default 10).

    Response 200::

        {
            "status": "success",
            "count": 10,
            "data": [ {"userId": 1, "id": 1, "title": "..."}, ... ]
        }

    Response 400::

        { "status": "error", "message": "'limit' must be an integer between 1 and 100." }

    Response 429::

        { "status": "error", "message": "External API rate limit exceeded." }

    Response 503::

        { "status": "error", "message": "Enrichment service temporarily unavailable." }
    """
    raw_limit = request.args.get("limit", "10")
    try:
        limit = int(raw_limit)
        if not (1 <= limit <= 100):
            raise ValueError
    except ValueError:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "'limit' must be an integer between 1 and 100.",
                }
            ),
            400,
        )

    try:
        posts = _service.get_posts_preview(limit=limit)
    except ExternalAPIRateLimitError as exc:
        logger.warning("Rate limited on /api/enrichment/posts: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 429
    except (ExternalAPITimeoutError, ExternalAPIUnavailableError) as exc:
        logger.error("Enrichment API unavailable: %s", exc)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Enrichment service temporarily unavailable.",
                }
            ),
            503,
        )
    except ExternalAPIError as exc:
        logger.error("Unexpected enrichment API error: %s", exc)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "An error occurred while fetching enrichment data.",
                }
            ),
            502,
        )

    return jsonify({"status": "success", "count": len(posts), "data": posts}), 200
