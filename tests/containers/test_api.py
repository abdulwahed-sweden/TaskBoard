"""Tests for the container operations REST API.

Mirrors the acceptance criteria of the tasks API: auth required, org scoping
(foreign objects 404 and never list), member-gated writes, plus the
container-specific guarantees — pin_hash is never exposed, status is read-only on
create, and the transition action enforces the workflow rules.
"""

import pytest
import test_helpers
from django.urls import reverse
from rest_framework.test import APIClient

from organizations.models import Membership
from containers.models import ServiceRequest

pytestmark = [pytest.mark.django_db]


def _api(role=Membership.Role.MEMBER):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user, org


# --- auth & scoping ----------------------------------------------------------

def test_unauthenticated_is_forbidden():
    assert APIClient().get(reverse("containers:customer-list")).status_code == 403


def test_member_can_create_and_list_customer():
    client, _user, org = _api()
    response = client.post(
        reverse("containers:customer-list"),
        {"organization": org.pk, "name": "Acme", "customer_number": "C1"},
    )
    assert response.status_code == 201
    listing = client.get(reverse("containers:customer-list"))
    assert listing.data["count"] == 1


def test_viewer_cannot_create_customer():
    client, _user, org = _api(role=Membership.Role.VIEWER)
    response = client.post(
        reverse("containers:customer-list"),
        {"organization": org.pk, "name": "Acme", "customer_number": "C1"},
    )
    assert response.status_code == 400  # serializer rejects the org for a viewer


def test_scoping_hides_foreign_objects():
    client, _user, org = _api()
    mine = test_helpers.create_containers_Customer(organization=org)
    foreign = test_helpers.create_containers_Customer()  # another org

    listing = client.get(reverse("containers:customer-list"))
    ids = {row["id"] for row in listing.data["results"]}
    assert mine.pk in ids
    assert foreign.pk not in ids
    assert client.get(
        reverse("containers:customer-detail", args=[foreign.pk])
    ).status_code == 404


# --- container-specific guarantees ------------------------------------------

def test_container_pin_hash_is_never_exposed():
    client, _user, org = _api()
    container = test_helpers.create_containers_Container(organization=org)
    response = client.get(reverse("containers:container-detail", args=[container.pk]))
    assert response.status_code == 200
    assert "pin_hash" not in response.data
    assert "qr_uid" in response.data


def test_service_request_status_is_read_only_on_create():
    client, _user, org = _api()
    customer = test_helpers.create_containers_Customer(organization=org)
    service_type = test_helpers.create_containers_ServiceType(organization=org)
    response = client.post(
        reverse("containers:servicerequest-list"),
        {
            "organization": org.pk,
            "customer": customer.pk,
            "service_type": service_type.pk,
            "reference": "SR-1",
            "status": ServiceRequest.Status.COMPLETED,  # ignored — read-only
        },
    )
    assert response.status_code == 201
    assert response.data["status"] == ServiceRequest.Status.NEW


def test_cross_org_customer_is_rejected():
    client, _user, org = _api()
    service_type = test_helpers.create_containers_ServiceType(organization=org)
    foreign_customer = test_helpers.create_containers_Customer()  # other org
    response = client.post(
        reverse("containers:servicerequest-list"),
        {
            "organization": org.pk,
            "customer": foreign_customer.pk,
            "service_type": service_type.pk,
            "reference": "SR-2",
        },
    )
    assert response.status_code == 400
    assert "customer" in response.data


# --- transition action -------------------------------------------------------

def _service_request(org):
    return test_helpers.create_containers_ServiceRequest(organization=org)


def test_transition_member_can_verify():
    client, _user, org = _api()
    sr = _service_request(org)
    response = client.post(
        reverse("containers:servicerequest-transition", args=[sr.pk]),
        {"to_status": ServiceRequest.Status.VERIFIED},
    )
    assert response.status_code == 200
    assert response.data["status"] == ServiceRequest.Status.VERIFIED
    sr.refresh_from_db()
    assert sr.status == ServiceRequest.Status.VERIFIED
    assert sr.activities.count() == 1


def test_transition_invalid_path_returns_400():
    client, _user, org = _api()
    sr = _service_request(org)
    response = client.post(
        reverse("containers:servicerequest-transition", args=[sr.pk]),
        {"to_status": ServiceRequest.Status.INVOICED},  # not reachable from new
    )
    assert response.status_code == 400
    sr.refresh_from_db()
    assert sr.status == ServiceRequest.Status.NEW


def test_transition_insufficient_role_returns_400():
    client, _user, org = _api()  # member
    sr = _service_request(org)
    response = client.post(
        reverse("containers:servicerequest-transition", args=[sr.pk]),
        {"to_status": ServiceRequest.Status.REJECTED, "note": "dup"},  # admin-only
    )
    assert response.status_code == 400
    sr.refresh_from_db()
    assert sr.status == ServiceRequest.Status.NEW


def test_transition_viewer_is_forbidden():
    client, _user, org = _api(role=Membership.Role.VIEWER)
    sr = _service_request(org)
    response = client.post(
        reverse("containers:servicerequest-transition", args=[sr.pk]),
        {"to_status": ServiceRequest.Status.VERIFIED},
    )
    assert response.status_code == 403  # object-level write permission denied


# --- schema still serves -----------------------------------------------------

def test_schema_endpoint_serves(client):
    assert client.get(reverse("schema")).status_code == 200
