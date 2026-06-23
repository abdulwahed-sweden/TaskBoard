"""Tests for the ServiceRequest transition layer (containers/workflow.py).

Pure logic — no database access — so these are unmarked and fast.
"""

import pytest
from django.core.exceptions import ValidationError

from organizations.models import Membership

from containers import workflow
from containers.models import ServiceRequest

Status = ServiceRequest.Status
OWNER = Membership.Role.OWNER
ADMIN = Membership.Role.ADMIN
MEMBER = Membership.Role.MEMBER
VIEWER = Membership.Role.VIEWER


# --- the happy path ----------------------------------------------------------

def test_happy_path_chain_is_all_valid():
    chain = [
        (Status.NEW, Status.VERIFIED, MEMBER),
        (Status.VERIFIED, Status.SCHEDULED, MEMBER),
        (Status.SCHEDULED, Status.ASSIGNED, MEMBER),
        (Status.ASSIGNED, Status.IN_PROGRESS, MEMBER),
        (Status.IN_PROGRESS, Status.COMPLETED, MEMBER),
        (Status.COMPLETED, Status.INVOICE_READY, MEMBER),
        (Status.INVOICE_READY, Status.INVOICED, ADMIN),
    ]
    for frm, to, role in chain:
        assert workflow.can_transition(role, frm, to), f"{frm} -> {to}"


# --- role gating -------------------------------------------------------------

def test_member_can_verify_viewer_cannot():
    assert workflow.can_transition(MEMBER, Status.NEW, Status.VERIFIED)
    assert not workflow.can_transition(VIEWER, Status.NEW, Status.VERIFIED)


def test_reject_and_cancel_are_admin_only():
    assert not workflow.can_transition(MEMBER, Status.NEW, Status.REJECTED)
    assert workflow.can_transition(ADMIN, Status.NEW, Status.REJECTED)
    assert not workflow.can_transition(MEMBER, Status.SCHEDULED, Status.CANCELLED)
    assert workflow.can_transition(ADMIN, Status.SCHEDULED, Status.CANCELLED)


def test_invoicing_is_admin_only():
    assert not workflow.can_transition(MEMBER, Status.INVOICE_READY, Status.INVOICED)
    assert workflow.can_transition(ADMIN, Status.INVOICE_READY, Status.INVOICED)


# --- invalid paths & terminals ----------------------------------------------

def test_invalid_transition_is_rejected_even_for_owner():
    assert not workflow.can_transition(OWNER, Status.NEW, Status.COMPLETED)
    assert workflow.transition_rule(Status.NEW, Status.COMPLETED) is None


def test_terminal_statuses_have_no_outgoing_transitions():
    for status in (Status.CANCELLED, Status.REJECTED, Status.INVOICED):
        assert workflow.is_terminal(status)
        assert workflow.allowed_transitions(OWNER, status) == []


def test_non_terminal_statuses_are_not_terminal():
    for status in (Status.NEW, Status.SCHEDULED, Status.COMPLETED):
        assert not workflow.is_terminal(status)


# --- notes -------------------------------------------------------------------

def test_requires_note_for_negative_transitions_only():
    assert workflow.requires_note(Status.NEW, Status.REJECTED)
    assert workflow.requires_note(Status.SCHEDULED, Status.CANCELLED)
    assert not workflow.requires_note(Status.NEW, Status.VERIFIED)


# --- allowed_transitions -----------------------------------------------------

def test_allowed_transitions_filters_by_role():
    member_targets = set(workflow.allowed_transitions(MEMBER, Status.NEW))
    admin_targets = set(workflow.allowed_transitions(ADMIN, Status.NEW))
    assert Status.VERIFIED in member_targets
    assert Status.REJECTED not in member_targets  # admin-only
    assert {Status.VERIFIED, Status.REJECTED, Status.CANCELLED} <= admin_targets


# --- validate_transition -----------------------------------------------------

def test_validate_transition_success_returns_target():
    assert (
        workflow.validate_transition(MEMBER, Status.NEW, Status.VERIFIED)
        == Status.VERIFIED
    )


def test_validate_transition_invalid_path_raises():
    with pytest.raises(ValidationError):
        workflow.validate_transition(OWNER, Status.NEW, Status.INVOICED)


def test_validate_transition_insufficient_role_raises():
    with pytest.raises(ValidationError):
        workflow.validate_transition(MEMBER, Status.NEW, Status.REJECTED, note="x")


def test_validate_transition_missing_required_note_raises():
    with pytest.raises(ValidationError):
        workflow.validate_transition(ADMIN, Status.NEW, Status.REJECTED, note="  ")


def test_validate_transition_with_note_succeeds():
    assert (
        workflow.validate_transition(
            ADMIN, Status.NEW, Status.REJECTED, note="duplicate request"
        )
        == Status.REJECTED
    )
