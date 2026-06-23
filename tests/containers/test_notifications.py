"""Tests for service-request transition email notifications."""

import pytest
import test_helpers

from organizations.models import Membership
from containers.models import NotificationLog, ServiceRequest
from containers.services import transition_service_request

pytestmark = [pytest.mark.django_db]

Status = ServiceRequest.Status


def _setup(customer_email="kund@example.com"):
    org = test_helpers.create_organizations_Organization()
    customer = test_helpers.create_containers_Customer(
        organization=org, email=customer_email
    )
    sr = test_helpers.create_containers_ServiceRequest(
        organization=org, customer=customer
    )
    membership = test_helpers.create_organizations_Membership(
        organization=org, role=Membership.Role.ADMIN
    )
    return sr, membership.user


def test_notable_transition_emails_customer(mailoutbox):
    sr, user = _setup()
    transition_service_request(sr, Status.VERIFIED, user=user)
    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.to == ["kund@example.com"]
    assert sr.reference in message.subject
    log = NotificationLog.objects.get()
    assert log.to_status == Status.VERIFIED
    assert log.sent is True
    assert log.recipient == "kund@example.com"


def test_intermediate_transition_does_not_email(mailoutbox):
    sr, user = _setup()
    # new -> verified -> scheduled -> assigned; "assigned" is not customer-facing.
    transition_service_request(sr, Status.VERIFIED, user=user)
    transition_service_request(sr, Status.SCHEDULED, user=user)
    mailoutbox.clear()
    transition_service_request(sr, Status.ASSIGNED, user=user)
    assert mailoutbox == []
    assert not NotificationLog.objects.filter(to_status=Status.ASSIGNED).exists()


def test_customer_without_email_is_not_notified(mailoutbox):
    sr, user = _setup(customer_email="")
    transition_service_request(sr, Status.VERIFIED, user=user)
    assert mailoutbox == []
    assert NotificationLog.objects.count() == 0
    # The transition itself still succeeded.
    sr.refresh_from_db()
    assert sr.status == Status.VERIFIED


def test_reject_notifies_customer(mailoutbox):
    sr, user = _setup()
    transition_service_request(sr, Status.REJECTED, user=user, note="duplicate")
    assert len(mailoutbox) == 1
    assert NotificationLog.objects.filter(
        to_status=Status.REJECTED, sent=True
    ).exists()
