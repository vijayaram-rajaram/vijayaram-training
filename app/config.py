"""
app/config.py
-------------
Application configuration classes.

Three environments are provided:

* ``DevelopmentConfig`` – SQLite file-based database, debug mode on.
* ``TestingConfig``     – SQLite **in-memory** database for isolated test runs.
* ``ProductionConfig``  – database URL read from the ``DATABASE_URL``
  environment variable.

Usage::

    from app.config import config
    app.config.from_object(config["testing"])
"""

import os


class _BaseConfig:
    """Shared defaults applied across all environments."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")


class DevelopmentConfig(_BaseConfig):
    """Local development: SQLite file on disk, debug output enabled."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", "sqlite:///customers_dev.db"
    )


class TestingConfig(_BaseConfig):
    """Test suite: in-memory SQLite, completely isolated per test run."""

    TESTING = True
    DEBUG = False
    # Each test receives a brand-new in-memory database – no shared state.
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"


class ProductionConfig(_BaseConfig):
    """Production: requires ``DATABASE_URL`` to be set in the environment."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI: str = os.environ.get("DATABASE_URL", "sqlite:///customers.db")


#: Mapping of environment name → config class used by the app factory.
config: dict[str, type[_BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
