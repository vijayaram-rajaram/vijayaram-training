"""
app/repositories/customer_repo.py
----------------------------------
Data-access layer for the ``customers`` table.

``CustomerRepository`` wraps all SQLAlchemy queries so that the service
layer never touches the ORM directly.  Isolating database calls here
makes it straightforward to:

* swap the underlying database engine without touching business logic,
* inject a mock repository in unit tests for fast, DB-free testing.

All methods operate within the current Flask-SQLAlchemy scoped session.
Callers (i.e. the service layer) are responsible for business-rule
validation; the repository handles *only* persistence.

Classes
-------
CustomerRepository
    CRUD operations against the ``customers`` table.
"""

from typing import Optional

from app.database import db
from app.models.customer import Customer


class CustomerRepository:
    """Low-level data access for the ``customers`` table.

    All methods use ``db.session`` which is a Flask-SQLAlchemy scoped
    session automatically bound to the current request or application
    context.
    """

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_all(self) -> list[Customer]:
        """Return every customer row ordered by ascending ID.

        Returns:
            list[Customer]: All Customer ORM objects, ordered by ``id``.
        """
        return db.session.query(Customer).order_by(Customer.id).all()

    def get_by_id(self, customer_id: int) -> Optional[Customer]:
        """Fetch a single customer by primary key.

        Args:
            customer_id (int): Primary key to look up.

        Returns:
            Customer | None: The matching ORM object, or ``None`` if not
                found.
        """
        return db.session.get(Customer, customer_id)

    def get_by_email(self, email: str) -> Optional[Customer]:
        """Fetch a customer whose email matches *email* (case-insensitive).

        Email comparison is performed after lower-casing so that
        ``Alice@Example.com`` and ``alice@example.com`` are treated as
        the same address.

        Args:
            email (str): Email address to search for.

        Returns:
            Customer | None: Matching customer, or ``None`` if not found.
        """
        return (
            db.session.query(Customer)
            .filter(Customer.email == email.lower())
            .first()
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, customer: Customer) -> Customer:
        """Persist a new customer record and return the saved object.

        After the INSERT the object is refreshed so that database-set
        fields (``id``, ``created_at``) are populated.

        Args:
            customer (Customer): Transient ORM object to insert.

        Returns:
            Customer: The same object after flush and refresh.
        """
        db.session.add(customer)
        db.session.commit()
        db.session.refresh(customer)
        return customer

    def save(self, customer: Customer) -> Customer:
        """Flush in-progress changes on a managed object and refresh it.

        Use this method after mutating attributes on an object that is
        already tracked by the session (i.e. an existing DB record).

        Args:
            customer (Customer): Managed ORM object with dirty attributes.

        Returns:
            Customer: The refreshed object reflecting the committed state.
        """
        db.session.commit()
        db.session.refresh(customer)
        return customer

    def delete(self, customer: Customer) -> None:
        """Remove a customer row from the database.

        Args:
            customer (Customer): The managed ORM object to delete.
        """
        db.session.delete(customer)
        db.session.commit()
