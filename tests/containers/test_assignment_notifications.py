"""Tests for driver-on-assigned notifications (fired when an Assignment is
created, via the post_save signal)."""

import pytest
import test_helpers

from containers.models import NotificationLog, ServiceRequest

pytestmark = [pytest.mark.django_db]


def test_assignment_emails_driver_with_email(mailoutbox):
    org = test_helpers.create_organizations_Organization()
    sr = test_helpers.create_containers_ServiceRequest(organization=org, reference="SR-9")
    driver = test_helpers.create_containers_Driver(
        organization=org, email="driver@example.com"
    )
    test_helpers.create_containers_Assignment(service_request=sr, driver=driver)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["driver@example.com"]
    assert "SR-9" in mailoutbox[0].subject
    log = NotificationLog.objects.get()
    assert log.recipient == "driver@example.com"
    assert log.to_status == ServiceRequest.Status.ASSIGNED
    assert log.sent is True


def test_assignment_falls_back_to_linked_user_email(mailoutbox):
    org = test_helpers.create_organizations_Organization()
    user = test_helpers.create_User(email="user@example.com")
    driver = test_helpers.create_containers_Driver(organization=org, user=user)  # no driver.email
    sr = test_helpers.create_containers_ServiceRequest(organization=org)
    test_helpers.create_containers_Assignment(service_request=sr, driver=driver)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["user@example.com"]


def test_assignment_without_any_email_is_silent(mailoutbox):
    org = test_helpers.create_organizations_Organization()
    driver = test_helpers.create_containers_Driver(organization=org)  # no email, no user
    sr = test_helpers.create_containers_ServiceRequest(organization=org)
    test_helpers.create_containers_Assignment(service_request=sr, driver=driver)

    assert mailoutbox == []
    assert NotificationLog.objects.count() == 0


def test_only_creation_notifies_not_updates(mailoutbox):
    org = test_helpers.create_organizations_Organization()
    driver = test_helpers.create_containers_Driver(
        organization=org, email="driver@example.com"
    )
    sr = test_helpers.create_containers_ServiceRequest(organization=org)
    assignment = test_helpers.create_containers_Assignment(
        service_request=sr, driver=driver
    )
    mailoutbox.clear()

    assignment.sequence = 5
    assignment.save(update_fields=["sequence"])  # an update, not a create
    assert mailoutbox == []
