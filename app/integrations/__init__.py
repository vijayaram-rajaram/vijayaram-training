"""
app/integrations
----------------
Third-party API client package.

Exposes a thin, reusable HTTP layer (``BaseHTTPClient``) and concrete
clients that depend on it.  All outbound credentials are sourced from
environment variables – never from code.

Public API
----------
BaseHTTPClient
    Base class with retry, timeout, API-key injection, and structured
    error mapping.
JSONPlaceholderClient
    Client for https://jsonplaceholder.typicode.com – used as the
    customer-enrichment data source.
"""

from app.integrations.http_client import BaseHTTPClient
from app.integrations.jsonplaceholder_client import JSONPlaceholderClient

__all__ = ["BaseHTTPClient", "JSONPlaceholderClient"]
