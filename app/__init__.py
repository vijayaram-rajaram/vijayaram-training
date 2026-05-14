"""
app/__init__.py
---------------
Flask application factory.

The factory pattern allows multiple application instances to coexist
(e.g., one for the development server, another for the test suite) and
avoids circular-import issues common in larger Flask projects.

Usage::

    from app import create_app

    app = create_app()            # development (default)
    app = create_app("testing")   # in-memory SQLite for tests
"""

import os

from flask import Flask

from app.config import config
from app.database import db


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_name (str | None): Key from ``app.config.config``.
            Defaults to ``FLASK_ENV`` env var, falling back to
            ``"development"`` when not set.

    Returns:
        Flask: The configured and ready-to-use application instance.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config["default"]))

    # ------------------------------------------------------------------
    # Production secret validation – fail fast before binding any port
    # ------------------------------------------------------------------
    if config_name == "production":
        from app.secrets import validate_production_secrets  # noqa: PLC0415

        validate_production_secrets()

    # ------------------------------------------------------------------
    # Initialise extensions
    # ------------------------------------------------------------------
    db.init_app(app)

    with app.app_context():
        # Create all tables that are not yet present in the database.
        # In production, prefer using Alembic migrations instead.
        db.create_all()

    # ------------------------------------------------------------------
    # Register blueprints
    # ------------------------------------------------------------------
    from app.routes.customer_routes import customer_bp  # noqa: PLC0415
    from app.routes.enrichment_routes import enrichment_bp  # noqa: PLC0415

    app.register_blueprint(customer_bp)
    app.register_blueprint(enrichment_bp)

    return app
