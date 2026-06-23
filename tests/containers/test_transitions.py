"""Tests for the ServiceRequest transition service + activity logging.

Exercises containers.services.transition_service_request, which ties the pure
transition layer (containers/workflow.py) to a persisted status change and an
append-only ServiceRequestActivity entry.
"""

import pytest
import test_helpers
from django.core.exceptions import ValidationError

from organizations.models import Membership

from containers.models import ServiceRequest, ServiceRequestActivity
from containers.services import transition_service_request

pytestmark = [pytest.mark.django_db]

Status = ServiceRequest.Status


def _member(organization, role):
    """A fresh user holding ``role`` in ``organization``."""
    membership = test_helpers.create_organizations_Membership(
        organization=organization, role=role
    )
    return membership.user


def test_transition_applies_status_and_logs_activity():
    request = test_helpers.create_containers_ServiceRequest()  # starts at NEW
    user = _member(request.organization, Membership.Role.MEMBER)

    activity = transition_service_request(request, Status.VERIFIED, user=user)

    request.refresh_from_db()
    assert request.status == Status.VERIFIED
    assert request.activities.count() == 1
    assert activity.action == ServiceRequestActivity.Action.STATUS_CHANGED
    assert activity.actor == user
    assert activity.detail == {"from": "new", "to": "verified", "note": ""}


def test_invalid_transition_raises_and_writes_nothing():
    request = test_helpers.create_containers_ServiceRequest()
    owner = _member(request.organization, Membership.Role.OWNER)

    with pytest.raises(ValidationError):
        transition_service_request(request, Status.INVOICED, user=owner)

    request.refresh_from_db()
    assert request.status == Status.NEW
    assert request.activities.count() == 0


def test_insufficient_role_raises_and_writes_nothing():
    request = test_helpers.create_containers_ServiceRequest()
    user = _member(request.organization, Membership.Role.MEMBER)

    # Rejecting is admin+; a member may not do it even with a note.
    with pytest.raises(ValidationError):
        transition_service_request(request, Status.REJECTED, user=user, note="dup")

    request.refresh_from_db()
    assert request.status == Status.NEW
    assert request.activities.count() == 0


def test_reject_requires_note_then_succeeds_with_one():
    request = test_helpers.create_containers_ServiceRequest()
    admin = _member(request.organization, Membership.Role.ADMIN)

    with pytest.raises(ValidationError):
        transition_service_request(request, Status.REJECTED, user=admin, note="  ")
    request.refresh_from_db()
    assert request.status == Status.NEW

    activity = transition_service_request(
        request, Status.REJECTED, user=admin, note="duplicate request"
    )
    request.refresh_from_db()
    assert request.status == Status.REJECTED
    assert activity.detail["note"] == "duplicate request"


def test_non_member_cannot_transition():
    request = test_helpers.create_containers_ServiceRequest()
    outsider = test_helpers.create_User()  # no membership in the org

    with pytest.raises(ValidationError):
        transition_service_request(request, Status.VERIFIED, user=outsider)

    request.refresh_from_db()
    assert request.status == Status.NEW
    assert request.activities.count() == 0


def test_multiple_transitions_log_in_newest_first_order():
    request = test_helpers.create_containers_ServiceRequest()
    user = _member(request.organization, Membership.Role.MEMBER)

    transition_service_request(request, Status.VERIFIED, user=user)
    transition_service_request(request, Status.SCHEDULED, user=user)

    request.refresh_from_db()
    assert request.status == Status.SCHEDULED
    assert request.activities.count() == 2
    latest = request.activities.first()  # ordering = -created, -id
    assert latest.detail == {"from": "verified", "to": "scheduled", "note": ""}
