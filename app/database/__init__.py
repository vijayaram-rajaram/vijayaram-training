"""
app/database/__init__.py
------------------------
SQLAlchemy extension instance shared across the entire application.

A single ``db`` object is created here and then registered with the Flask
application inside the factory function (``app/__init__.py``).  Import
this object wherever you need access to the ORM session or to declare
model classes::

    from app.database import db

    class MyModel(db.Model):
        ...
"""

from flask_sqlalchemy import SQLAlchemy

#: The shared Flask-SQLAlchemy extension instance.
db: SQLAlchemy = SQLAlchemy()
