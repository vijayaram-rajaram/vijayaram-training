"""
app/integrations/jsonplaceholder_client.py
-------------------------------------------
Concrete HTTP client for the JSONPlaceholder REST API.

JSONPlaceholder (https://jsonplaceholder.typicode.com) is a free,
public fake REST API used here as a **customer enrichment** data source.
It returns realistic-looking user profiles, posts, todos, and albums.

In a production scenario you would swap this client for a real paid
enrichment provider (e.g. Clearbit, FullContact) simply by:

    1. Changing ``ENRICHMENT_API_BASE_URL`` in your environment.
    2. Setting ``ENRICHMENT_API_KEY`` to your real key.
    3. Overriding ``_get_headers()`` if the provider uses a different
       authentication scheme (e.g. ``X-API-Key``).

All configuration is read from environment variables so the client can
be instantiated outside of a Flask application context (e.g. at module
load time or in test fixtures), matching how ``_BaseConfig`` resolves
the same values.

API coverage
------------
get_users()              – List all users (≤ 10 results from sandbox).
get_user(user_id)        – Fetch a single user by ID (1–10).
get_posts(limit)         – List posts with an optional result cap.
get_posts_by_user(uid)   – Fetch posts authored by a specific user.
get_todos_by_user(uid)   – Fetch to-do items assigned to a specific user.
get_albums_by_user(uid)  – Fetch albums belonging to a specific user.
"""

from __future__ import annotations

import logging

from app.integrations.http_client import BaseHTTPClient
from app.secrets import load_secret

logger = logging.getLogger(__name__)

#: Maximum number of enrichment posts returned in a profile summary.
_POST_PREVIEW_LIMIT = 5

#: JSONPlaceholder only has 10 users (IDs 1–10).
_MAX_USER_ID = 10


def _map_customer_to_user_id(customer_id: int) -> int:
    """Map an arbitrary customer ID to a valid JSONPlaceholder user ID.

    JSONPlaceholder provides exactly 10 users (IDs 1–10).  We use a
    modulo mapping so every customer ID resolves to a deterministic,
    valid user ID.

    Args:
        customer_id (int): Internal customer primary key.

    Returns:
        int: A user ID in the range [1, 10].
    """
    return (customer_id % _MAX_USER_ID) or _MAX_USER_ID


class JSONPlaceholderClient(BaseHTTPClient):
    """HTTP client for the JSONPlaceholder enrichment API.

    Configuration is read from environment variables using the same
    names and defaults as ``app.config._BaseConfig``.  This allows the
    client to be instantiated at module load time (before a Flask
    application context is available) while still honouring runtime
    configuration in all environments.

    Environment variables
    ---------------------
    ENRICHMENT_API_BASE_URL   – Base URL (default: https://jsonplaceholder.typicode.com)
    ENRICHMENT_API_KEY        – Optional Bearer token (default: none)
    ENRICHMENT_API_TIMEOUT    – Per-request timeout seconds (default: 10)
    ENRICHMENT_API_MAX_RETRIES – Max retry attempts (default: 3)
    ENRICHMENT_API_BACKOFF    – Exponential back-off multiplier (default: 0.5)
    """

    def __init__(self) -> None:
        super().__init__(
            base_url=(
                load_secret("ENRICHMENT_API_BASE_URL")
                or "https://jsonplaceholder.typicode.com"
            ),
            # load_secret resolves from env var first, then the configured
            # vault backend (e.g. AWS Secrets Manager).  Returns None when
            # the key is absent, which disables the Authorization header.
            api_key=load_secret("ENRICHMENT_API_KEY"),
            timeout=int(load_secret("ENRICHMENT_API_TIMEOUT") or "10"),
            max_retries=int(load_secret("ENRICHMENT_API_MAX_RETRIES") or "3"),
            backoff=float(load_secret("ENRICHMENT_API_BACKOFF") or "0.5"),
        )


    # ------------------------------------------------------------------
    # User endpoints
    # ------------------------------------------------------------------

    def get_users(self) -> list[dict]:
        """Fetch all available users from the enrichment API.

        Returns:
            list[dict]: List of user records.
        """
        return self.get("/users")

    def get_user(self, user_id: int) -> dict:
        """Fetch a single user by their enrichment-API ID.

        Args:
            user_id (int): User ID as understood by the remote API
                (1–10 for JSONPlaceholder).

        Returns:
            dict: User record containing ``name``, ``email``,
                ``address``, ``company``, etc.
        """
        return self.get(f"/users/{user_id}")

    # ------------------------------------------------------------------
    # Post endpoints
    # ------------------------------------------------------------------

    def get_posts(self, limit: int | None = None) -> list[dict]:
        """Fetch posts, optionally capping the result set.

        Args:
            limit (int | None): Maximum number of posts to return.
                ``None`` returns all available posts (up to 100 for
                JSONPlaceholder).

        Returns:
            list[dict]: Post records.
        """
        posts: list[dict] = self.get("/posts")
        return posts[:limit] if limit is not None else posts

    def get_posts_by_user(self, user_id: int) -> list[dict]:
        """Fetch all posts authored by a given user.

        Args:
            user_id (int): Remote-API user ID.

        Returns:
            list[dict]: Posts belonging to *user_id*.
        """
        return self.get("/posts", params={"userId": user_id})

    # ------------------------------------------------------------------
    # Todo endpoints
    # ------------------------------------------------------------------

    def get_todos_by_user(self, user_id: int) -> list[dict]:
        """Fetch all to-do items assigned to a given user.

        Args:
            user_id (int): Remote-API user ID.

        Returns:
            list[dict]: To-do records with ``title`` and ``completed`` fields.
        """
        return self.get("/todos", params={"userId": user_id})

    # ------------------------------------------------------------------
    # Album endpoints
    # ------------------------------------------------------------------

    def get_albums_by_user(self, user_id: int) -> list[dict]:
        """Fetch all albums belonging to a given user.

        Args:
            user_id (int): Remote-API user ID.

        Returns:
            list[dict]: Album records.
        """
        return self.get("/albums", params={"userId": user_id})

    # ------------------------------------------------------------------
    # Enrichment convenience helper
    # ------------------------------------------------------------------

    def get_enrichment_profile(self, customer_id: int) -> dict:
        """Return a full enrichment bundle for a customer.

        Maps the internal *customer_id* to a stable external user ID and
        fetches the external user profile, a preview of their recent
        posts, and a summary of their open to-do items.

        Args:
            customer_id (int): Internal customer primary key.

        Returns:
            dict: Enrichment bundle with keys:
                * ``external_user_id`` – the remote user ID used.
                * ``profile`` – full remote user record.
                * ``recent_posts`` – up to 5 most recent post titles.
                * ``open_todos`` – count of incomplete to-do items.
        """
        user_id = _map_customer_to_user_id(customer_id)

        profile = self.get_user(user_id)
        posts = self.get_posts_by_user(user_id)
        todos = self.get_todos_by_user(user_id)

        recent_posts = [
            {"id": p["id"], "title": p["title"]}
            for p in posts[:_POST_PREVIEW_LIMIT]
        ]
        open_todos = sum(1 for t in todos if not t.get("completed", True))

        return {
            "external_user_id": user_id,
            "profile": profile,
            "recent_posts": recent_posts,
            "open_todos": open_todos,
        }
