"""
app/models/customer.py
----------------------
Customer ORM model backed by SQLAlchemy.

The ``Customer`` class maps to the ``customers`` database table and
exposes a ``to_dict`` helper for JSON serialisation.  It replaces the
previous dataclass-based model to support real database persistence.

Database columns
----------------
id         – Auto-incremented integer primary key.
name       – Full name of the customer (up to 255 chars).
email      – Unique, lower-cased email address (indexed for fast lookup).
phone      – Contact phone number (up to 50 chars).
address    – Physical address (up to 500 chars).
created_at – UTC timestamp set automatically on INSERT.
"""

from datetime import datetime, timezone

from app.database import db


class Customer(db.Model):
    """Persistent customer record mapped to the ``customers`` table.

    Attributes:
        id (int): Auto-incremented primary key.
        name (str): Full name of the customer.
        email (str): Unique email address (stored lower-cased).
        phone (str): Contact phone number.
        address (str): Physical address.
        created_at (datetime): UTC timestamp of record creation.
    """

    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    phone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(500), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        """Serialise the record to a JSON-compatible dictionary.

        Returns:
            dict: Mapping of all column names to their current values.
                  ``created_at`` is returned as an ISO-8601 string.
        """
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Customer id={self.id} email={self.email!r}>"

    @staticmethod
    def from_dict(data: dict) -> "Customer":
        """Deserialize a customer from a plain dictionary.

        Args:
            data (dict): Dictionary with customer fields.

        Returns:
            Customer: Populated Customer instance.

        Raises:
            KeyError: If a required field is absent.
        """
        return Customer(
            name=data["name"],
            email=data["email"],
            phone=data["phone"],
            address=data["address"],
        )
