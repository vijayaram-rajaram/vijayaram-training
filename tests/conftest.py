"""
tests/conftest.py
-----------------
Shared pytest fixtures for the entire test suite.

Design decisions
----------------
* Each test receives a **fresh in-memory SQLite database** (function scope)
  so tests are fully isolated – no shared state between test functions.
* The Flask app runs in ``"testing"`` mode, which sets
  ``SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"`` and ``TESTING = True``.
* The ``client`` fixture provides a Flask test client wired to the
  testing app for HTTP-layer integration tests.
* The ``db`` fixture exposes the SQLAlchemy instance within the active
  application context so repository tests can manipulate the session
  directly.

Usage in tests::

    def test_something(client, db):
        ...

    def test_service(app):
        service = CustomerService()
        ...
"""

import pytest

from app import create_app
from app.database import db as _db


@pytest.fixture()
def app():
    """Provide a Flask application configured for testing.

    * Uses an in-memory SQLite database.
    * Creates all tables before the test and drops them afterwards.
    * Pushes an application context for the duration of the test so
      SQLAlchemy operations work without an HTTP request.
    """
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client for HTTP-layer integration tests."""
    return app.test_client()


@pytest.fixture()
def db(app):
    """SQLAlchemy DB instance with an active app context.

    Yields the same ``db`` object that models and repositories use so
    test helpers can directly insert seed data via ``db.session``.
    """
    yield _db
