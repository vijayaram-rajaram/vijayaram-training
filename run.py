"""
run.py
------
Development entry point for the Customer CRUD API.

Usage::

    python run.py

The server starts on http://127.0.0.1:5000 in debug mode.
Set the ``FLASK_ENV`` environment variable to ``production`` and use a
production WSGI server (e.g., gunicorn) for real deployments.
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
