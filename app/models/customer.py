"""
app/models/customer.py
----------------------
Customer data model using Python dataclasses.

A Customer represents a client record with contact and address information.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class Customer:
    """Represents a customer record.

    Attributes:
        id (int): Unique identifier.
        name (str): Full name of the customer.
        email (str): Email address (must be unique).
        phone (str): Contact phone number.
        address (str): Physical address.
        created_at (str): ISO-8601 UTC timestamp of record creation.
    """

    id: int
    name: str
    email: str
    phone: str
    address: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """Serialize the customer to a plain dictionary.

        Returns:
            dict: All customer fields as key-value pairs.
        """
        return asdict(self)

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
            id=data["id"],
            name=data["name"],
            email=data["email"],
            phone=data["phone"],
            address=data["address"],
            created_at=data.get(
                "created_at",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
