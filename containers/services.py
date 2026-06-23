"""Service-layer helpers for the containers app.

Kept separate from models/views so the same logic is reusable from a management
command, the (later) signup flow, the admin, and tests — mirroring
``organizations/services.py``.
"""

from .models import ServiceType

# Canonical catalog of services a container operations company offers. Seeded
# per-organization (tenancy requires an owning org), idempotently on
# ``(organization, code)``.
STANDARD_SERVICE_TYPES = [
    {"code": "emptying", "name": "Container Emptying", "category": "waste", "requires_pin": True},
    {"code": "replacement", "name": "Container Replacement", "category": "waste", "requires_pin": True},
    {"code": "rental", "name": "Container Rental", "category": "rental", "requires_pin": True},
    {"code": "construction_waste", "name": "Construction Waste", "category": "waste", "requires_pin": True},
    {"code": "electrical_waste", "name": "Electrical Waste", "category": "waste", "requires_pin": True},
    {"code": "asbestos", "name": "Asbestos Job", "category": "hazardous", "requires_pin": True},
    {"code": "quote_request", "name": "Quote Request", "category": "sales", "requires_pin": False},
]


def seed_service_types(organization):
    """Create the standard service types for ``organization`` where missing.

    Idempotent: a type already present (matched by ``code`` within the org) is
    left untouched — re-running never duplicates or overwrites. Returns the list
    of newly created :class:`ServiceType` instances (empty when all existed).
    """
    created = []
    for spec in STANDARD_SERVICE_TYPES:
        obj, was_created = ServiceType.objects.get_or_create(
            organization=organization,
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "category": spec["category"],
                "requires_pin": spec["requires_pin"],
            },
        )
        if was_created:
            created.append(obj)
    return created
