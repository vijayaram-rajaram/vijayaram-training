"""
app/__init__.py
---------------
Flask application factory.

Usage:
    from app import create_app
    app = create_app()
"""

from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns:
        Flask: The configured application instance.
    """
    app = Flask(__name__)

    # Register blueprints
    from app.routes.customer_routes import customer_bp
    app.register_blueprint(customer_bp)

    return app
