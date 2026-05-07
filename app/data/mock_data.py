"""
app/data/mock_data.py
---------------------
In-memory data store seeded with mock customer records.

This module acts as а lightweight "database" for the application.
The store is a plain Python dict keyed by customer ID.

Functions
---------
get_store()
    Return the live mutable store dict.
get_next_id()
    Return the next auto-increment ID and advance the counter.
reset_store()
    Restore the store to its initial seed state (intended for use in tests).
"""

from copy import deepcopy

from app.models.customer import Customer


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_SEED_DATA: dict[int, Customer] = {
    1: Customer(
        id=1,
        name="Alice Johnson",
        email="alice.johnson@example.com",
        phone="555-0101",
        address="123 Main St, New York, NY 10001",
        created_at="2024-01-15T10:00:00+00:00",
    ),
    2: Customer(
        id=2,
        name="Bob Smith",
        email="bob.smith@example.com",
        phone="555-0102",
        address="456 Oak Ave, Los Angeles, CA 90001",
        created_at="2024-02-20T11:30:00+00:00",
    ),
    3: Customer(
        id=3,
        name="Carol Williams",
        email="carol.williams@example.com",
        phone="555-0103",
        address="789 Pine Rd, Chicago, IL 60601",
        created_at="2024-03-05T09:15:00+00:00",
    ),
    4: Customer(
        id=4,
        name="David Brown",
        email="david.brown@example.com",
        phone="555-0104",
        address="321 Elm St, Houston, TX 77001",
        created_at="2024-04-12T14:45:00+00:00",
    ),
    5: Customer(
        id=5,
        name="Eva Martinez",
        email="eva.martinez@example.com",
        phone="555-0105",
        address="654 Maple Dr, Phoenix, AZ 85001",
        created_at="2024-05-18T08:00:00+00:00",
    ),
}

# ---------------------------------------------------------------------------
# Live store and ID counter (module-level mutable state)
# ---------------------------------------------------------------------------

_store: dict[int, Customer] = {}
_id_counter: list[int] = [0]  # wrapped in list so it is mutable from helpers


def _initialize() -> None:
    """Populate the store from seed data."""
    global _store
    _store = deepcopy(_SEED_DATA)
    _id_counter[0] = max(_store.keys()) if _store else 0


_initialize()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_store() -> dict[int, Customer]:
    """Return the live mutable store.

    Returns:
        dict[int, Customer]: The current in-memory customer store.
    """
    return _store


def get_next_id() -> int:
    """Advance the ID counter and return the new value.

    Returns:
        int: The next unique customer ID.
    """
    _id_counter[0] += 1
    return _id_counter[0]


def reset_store() -> None:
    """Reset the store to its original seed state.

    This function is provided for test isolation — call it in ``setUp``
    to guarantee a clean, predictable state for every test case.
    """
    _initialize()
