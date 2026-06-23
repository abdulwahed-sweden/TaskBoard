"""Status lifecycle and transition rules for :class:`ServiceRequest`.

The configurable engine (``organizations/workflow.py``) intentionally allows any
status to follow any other; the container operations business needs a fixed,
role-aware lifecycle instead. This module is that single source of truth: a
transition table plus pure predicates, mirroring
``organizations.permissions.has_role`` in style.

It performs no database writes and is independent of any form/serializer.
Wiring it into the admin / forms / API and recording transitions to an activity
log arrive in a later, separately approved phase — this slice is the rules
engine only.
"""

from django.core.exceptions import ValidationError

from organizations.models import Membership, role_rank

from .models import ServiceRequest

Status = ServiceRequest.Status

OWNER = Membership.Role.OWNER
ADMIN = Membership.Role.ADMIN
MEMBER = Membership.Role.MEMBER
VIEWER = Membership.Role.VIEWER

# Ordered "happy path" for display purposes (side exits omitted).
STATUS_ORDER = [
    Status.NEW,
    Status.VERIFIED,
    Status.SCHEDULED,
    Status.ASSIGNED,
    Status.IN_PROGRESS,
    Status.COMPLETED,
    Status.INVOICE_READY,
    Status.INVOICED,
]

# Statuses from which no further transition is allowed.
TERMINAL_STATUSES = frozenset(
    {Status.CANCELLED, Status.REJECTED, Status.INVOICED}
)

# from_status -> { to_status: {"min_role": <Role>, "requires_note": bool} }
# Scheduling/operational moves are member+; rejecting, cancelling and invoicing
# are admin+. Negative transitions (reject/cancel) require an explanatory note.
TRANSITIONS = {
    Status.NEW: {
        Status.VERIFIED: {"min_role": MEMBER, "requires_note": False},
        Status.REJECTED: {"min_role": ADMIN, "requires_note": True},
        Status.CANCELLED: {"min_role": ADMIN, "requires_note": True},
    },
    Status.VERIFIED: {
        Status.SCHEDULED: {"min_role": MEMBER, "requires_note": False},
        Status.REJECTED: {"min_role": ADMIN, "requires_note": True},
        Status.CANCELLED: {"min_role": ADMIN, "requires_note": True},
    },
    Status.SCHEDULED: {
        Status.ASSIGNED: {"min_role": MEMBER, "requires_note": False},
        Status.CANCELLED: {"min_role": ADMIN, "requires_note": True},
    },
    Status.ASSIGNED: {
        Status.IN_PROGRESS: {"min_role": MEMBER, "requires_note": False},
        Status.CANCELLED: {"min_role": ADMIN, "requires_note": True},
    },
    Status.IN_PROGRESS: {
        Status.COMPLETED: {"min_role": MEMBER, "requires_note": False},
        Status.CANCELLED: {"min_role": ADMIN, "requires_note": True},
    },
    Status.COMPLETED: {
        Status.INVOICE_READY: {"min_role": MEMBER, "requires_note": False},
    },
    Status.INVOICE_READY: {
        Status.INVOICED: {"min_role": ADMIN, "requires_note": False},
    },
}


def transition_rule(from_status, to_status):
    """The rule dict for a from→to transition, or ``None`` if not allowed."""
    return TRANSITIONS.get(from_status, {}).get(to_status)


def is_terminal(status):
    """Whether ``status`` permits no further transitions."""
    return status in TERMINAL_STATUSES


def requires_note(from_status, to_status):
    """Whether moving from→to requires an explanatory note."""
    rule = transition_rule(from_status, to_status)
    return bool(rule and rule["requires_note"])


def can_transition(role, from_status, to_status):
    """True if a holder of Membership ``role`` may move a request from
    ``from_status`` to ``to_status``.

    A pure role-rank check against the transition table; it does not consider
    the note requirement — use :func:`validate_transition` for full enforcement.
    """
    rule = transition_rule(from_status, to_status)
    if rule is None:
        return False
    return role_rank(role) >= role_rank(rule["min_role"])


def allowed_transitions(role, from_status):
    """Target statuses ``role`` is permitted to move ``from_status`` to."""
    return [
        to_status
        for to_status in TRANSITIONS.get(from_status, {})
        if can_transition(role, from_status, to_status)
    ]


def validate_transition(role, from_status, to_status, note=""):
    """Validate a requested transition; return ``to_status`` or raise.

    Enforces, in order: the transition exists in the table, the role rank is
    high enough, and a note is present where the rule requires one. Raises
    ``django.core.exceptions.ValidationError`` on any failure.
    """
    rule = transition_rule(from_status, to_status)
    if rule is None:
        raise ValidationError(
            f"Cannot move a request from '{from_status}' to '{to_status}'."
        )
    if role_rank(role) < role_rank(rule["min_role"]):
        raise ValidationError(
            f"Your role is not permitted to move a request to '{to_status}'."
        )
    if rule["requires_note"] and not (note or "").strip():
        raise ValidationError(
            f"A note is required to move a request to '{to_status}'."
        )
    return to_status
