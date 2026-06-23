"""Tests for the server-rendered operations UI and Swedish i18n."""

import pytest
import test_helpers
from django.urls import reverse

from organizations.models import Membership
from containers.models import ServiceRequest

pytestmark = [pytest.mark.django_db]


def _login_member(client, role=Membership.Role.MEMBER):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    client.force_login(user)  # active org resolves to the user's first org
    return user, org


# --- auth --------------------------------------------------------------------

def test_dashboard_requires_login(client):
    response = client.get(reverse("containers:dashboard"))
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_dashboard_renders_for_member(client):
    _login_member(client)
    response = client.get(reverse("containers:dashboard"))
    assert response.status_code == 200


# --- service requests --------------------------------------------------------

def test_request_list_and_filter(client):
    _user, org = _login_member(client)
    test_helpers.create_containers_ServiceRequest(organization=org, reference="SR-AAA")
    url = reverse("containers:servicerequest_list")
    assert b"SR-AAA" in client.get(url).content
    # A non-matching status filter hides it.
    filtered = client.get(url, {"status": ServiceRequest.Status.COMPLETED})
    assert b"SR-AAA" not in filtered.content


def test_request_detail_scoping(client):
    _user, _org = _login_member(client)
    foreign = test_helpers.create_containers_ServiceRequest()  # another org
    response = client.get(
        reverse("containers:servicerequest_detail", args=[foreign.pk])
    )
    assert response.status_code == 404


def test_member_can_transition_from_detail(client):
    _user, org = _login_member(client)
    sr = test_helpers.create_containers_ServiceRequest(organization=org)
    response = client.post(
        reverse("containers:servicerequest_transition", args=[sr.pk]),
        {"to_status": ServiceRequest.Status.VERIFIED},
    )
    assert response.status_code == 302
    sr.refresh_from_db()
    assert sr.status == ServiceRequest.Status.VERIFIED
    assert sr.activities.count() == 1


def test_invalid_transition_keeps_status(client):
    _user, org = _login_member(client)
    sr = test_helpers.create_containers_ServiceRequest(organization=org)
    client.post(
        reverse("containers:servicerequest_transition", args=[sr.pk]),
        {"to_status": ServiceRequest.Status.INVOICED},  # unreachable from new
    )
    sr.refresh_from_db()
    assert sr.status == ServiceRequest.Status.NEW


def test_viewer_transition_is_blocked_by_service(client):
    _user, org = _login_member(client, role=Membership.Role.VIEWER)
    sr = test_helpers.create_containers_ServiceRequest(organization=org)
    client.post(
        reverse("containers:servicerequest_transition", args=[sr.pk]),
        {"to_status": ServiceRequest.Status.VERIFIED},
    )
    sr.refresh_from_db()
    assert sr.status == ServiceRequest.Status.NEW
    assert sr.activities.count() == 0


# --- reference lists ---------------------------------------------------------

def test_customer_container_driver_lists_render(client):
    _user, org = _login_member(client)
    test_helpers.create_containers_Customer(organization=org, name="Acme AB")
    test_helpers.create_containers_Driver(organization=org, name="Olle")
    test_helpers.create_containers_Container(organization=org)
    assert b"Acme AB" in client.get(reverse("containers:customer_list")).content
    assert b"Olle" in client.get(reverse("containers:driver_list")).content
    assert client.get(reverse("containers:container_list")).status_code == 200


# --- i18n --------------------------------------------------------------------

def test_default_language_is_english(client):
    _login_member(client)
    response = client.get(reverse("containers:dashboard"))
    assert b"Service requests" in response.content  # English nav label


def test_swedish_locale_translates_ui(client):
    _login_member(client)
    response = client.get(
        reverse("containers:dashboard"), HTTP_ACCEPT_LANGUAGE="sv"
    )
    content = response.content.decode()
    assert "Översikt" in content          # Dashboard
    assert "Serviceförfrågningar" in content  # Service requests
