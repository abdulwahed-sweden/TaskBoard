"""Service-layer helpers for the containers app.

Kept separate from models/views so the same logic is reusable from a management
command, the (later) signup flow, the admin, and tests — mirroring
``organizations/services.py``.
"""

from django.db import transaction

from organizations.models import Membership

from . import workflow
from .models import ServiceRequestActivity, ServiceType

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


def _role_for(user, organization):
    """The user's Membership role in ``organization``, or ``None`` if they are
    anonymous or not a member. Mirrors the lookup inside
    ``organizations.permissions.has_role`` without modifying that app."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    membership = (
        Membership.objects.filter(user=user, organization=organization)
        .only("role")
        .first()
    )
    return membership.role if membership else None


def transition_service_request(service_request, to_status, *, user, note=""):
    """Validate and apply a lifecycle transition, recording an activity entry.

    Resolves ``user``'s role in the request's organization, enforces the
    transition rules (``containers/workflow.py``), persists the new status, and
    appends a STATUS_CHANGED :class:`ServiceRequestActivity`. The status change
    and the log entry are written atomically. Returns the created activity.

    Raises ``django.core.exceptions.ValidationError`` if the move is not
    permitted (unknown transition, insufficient role, or a missing required
    note) — in that case nothing is written.
    """
    role = _role_for(user, service_request.organization)
    from_status = service_request.status

    # Raises before any write when the transition is not allowed.
    workflow.validate_transition(role, from_status, to_status, note=note)

    actor = user if (user is not None and getattr(user, "is_authenticated", False)) else None
    actor_name = actor.get_username() if actor is not None else "Someone"

    with transaction.atomic():
        service_request.status = to_status
        service_request.save(update_fields=["status", "updated"])
        return ServiceRequestActivity.objects.create(
            service_request=service_request,
            actor=actor,
            action=ServiceRequestActivity.Action.STATUS_CHANGED,
            description=f"{actor_name} changed status to {service_request.get_status_display()}.",
            detail={"from": from_status, "to": to_status, "note": note},
        )
