"""Tests for the public, PIN-gated QR customer portal.

Covers the security boundary (PIN gate, no pre-PIN disclosure, server-derived
tenancy, honeypot, rate limits) and the happy-path submission.
"""

from datetime import timedelta

import pytest
import test_helpers
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from containers.models import Container, ServiceRequest
from containers.services import set_container_pin

pytestmark = [pytest.mark.django_db]

PIN = "2468"


@pytest.fixture(autouse=True)
def _clear_cache():
    # The rate limiter uses the process cache; isolate every test.
    cache.clear()
    yield
    cache.clear()


def _setup(pin=PIN, **container_kwargs):
    org = test_helpers.create_organizations_Organization()
    customer = test_helpers.create_containers_Customer(organization=org)
    site = test_helpers.create_containers_Site(customer=customer)
    container = test_helpers.create_containers_Container(
        organization=org, customer=customer, site=site, **container_kwargs
    )
    set_container_pin(container, pin)
    service_type = test_helpers.create_containers_ServiceType(organization=org)
    return org, customer, container, service_type


def _verify(client, container, pin=PIN):
    return client.post(reverse("portal:verify", args=[container.qr_uid]), {"pin": pin})


def _valid_payload(service_type):
    return {
        "service_type": service_type.pk,
        "requested_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
        "contact_name": "Jane Doe",
        "contact_phone": "0700000000",
        "notes": "Leave by the gate.",
    }


# --- landing / lookup --------------------------------------------------------

def test_landing_shows_pin_form(client):
    _org, _customer, container, _st = _setup()
    response = client.get(reverse("portal:landing", args=[container.qr_uid]))
    assert response.status_code == 200
    assert b"PIN" in response.content


def test_unknown_qr_uid_is_404(client):
    response = client.get(reverse("portal:landing", args=["0" * 32]))
    assert response.status_code == 404


def test_inactive_container_is_404(client):
    org = test_helpers.create_organizations_Organization()
    container = test_helpers.create_containers_Container(
        organization=org, status=Container.Status.REMOVED
    )
    set_container_pin(container, PIN)
    response = client.get(reverse("portal:landing", args=[container.qr_uid]))
    assert response.status_code == 404


# --- PIN gate ----------------------------------------------------------------

def test_correct_pin_grants_access(client):
    _org, _customer, container, _st = _setup()
    response = _verify(client, container)
    assert response.status_code == 302
    assert response.url == reverse("portal:request", args=[container.qr_uid])
    # The request page is now reachable.
    assert client.get(reverse("portal:request", args=[container.qr_uid])).status_code == 200


def test_wrong_pin_denies_access(client):
    _org, _customer, container, _st = _setup()
    response = _verify(client, container, pin="9999")
    assert response.status_code == 200  # re-rendered with an error, no redirect
    # Still unverified: the request page bounces back to the landing.
    follow = client.get(reverse("portal:request", args=[container.qr_uid]))
    assert follow.status_code == 302
    assert follow.url == reverse("portal:landing", args=[container.qr_uid])


def test_request_page_requires_verification(client):
    _org, _customer, container, _st = _setup()
    response = client.get(reverse("portal:request", args=[container.qr_uid]))
    assert response.status_code == 302
    assert response.url == reverse("portal:landing", args=[container.qr_uid])


# --- no sensitive disclosure -------------------------------------------------

def test_request_page_hides_sensitive_data(client):
    org = test_helpers.create_organizations_Organization()
    customer = test_helpers.create_containers_Customer(
        organization=org, customer_number="SECRET-ACCT-001"
    )
    site = test_helpers.create_containers_Site(customer=customer)
    container = test_helpers.create_containers_Container(
        organization=org, customer=customer, site=site,
        serial_number="SECRET-SERIAL-XYZ",
    )
    set_container_pin(container, PIN)
    test_helpers.create_containers_ServiceType(organization=org)

    _verify(client, container)
    response = client.get(reverse("portal:request", args=[container.qr_uid]))
    body = response.content
    assert response.status_code == 200
    assert org.name.encode() in body            # operator name is shown
    assert b"SECRET-ACCT-001" not in body       # customer_number is not
    assert b"SECRET-SERIAL-XYZ" not in body     # serial_number is not
    assert b"pin_hash" not in body


# --- submission --------------------------------------------------------------

def test_submission_creates_service_request(client):
    org, customer, container, service_type = _setup()
    _verify(client, container)
    response = client.post(
        reverse("portal:request", args=[container.qr_uid]),
        _valid_payload(service_type),
    )
    assert response.status_code == 302
    sr = ServiceRequest.objects.get()
    assert sr.organization == org
    assert sr.customer == customer
    assert sr.container == container
    assert sr.site == container.site
    assert sr.service_type == service_type
    assert sr.source == ServiceRequest.Source.QR
    assert sr.status == ServiceRequest.Status.NEW
    assert sr.contact_name == "Jane Doe"
    assert response.url == reverse("portal:done", args=[container.qr_uid, sr.reference])


def test_honeypot_blocks_submission(client):
    _org, _customer, container, service_type = _setup()
    _verify(client, container)
    payload = _valid_payload(service_type)
    payload["website"] = "http://spam.example"  # bots fill this hidden field
    response = client.post(reverse("portal:request", args=[container.qr_uid]), payload)
    assert response.status_code == 200  # re-rendered, not redirected
    assert ServiceRequest.objects.count() == 0


def test_past_date_is_rejected(client):
    _org, _customer, container, service_type = _setup()
    _verify(client, container)
    payload = _valid_payload(service_type)
    payload["requested_date"] = (timezone.localdate() - timedelta(days=1)).isoformat()
    response = client.post(reverse("portal:request", args=[container.qr_uid]), payload)
    assert response.status_code == 200
    assert ServiceRequest.objects.count() == 0


def test_foreign_service_type_is_rejected(client):
    _org, _customer, container, _st = _setup()
    other_org = test_helpers.create_organizations_Organization()
    foreign_type = test_helpers.create_containers_ServiceType(organization=other_org)
    _verify(client, container)
    payload = _valid_payload(foreign_type)
    response = client.post(reverse("portal:request", args=[container.qr_uid]), payload)
    assert response.status_code == 200
    assert ServiceRequest.objects.count() == 0


# --- rate limiting -----------------------------------------------------------

def test_pin_verification_is_rate_limited(client):
    _org, _customer, container, _st = _setup()
    url = reverse("portal:verify", args=[container.qr_uid])
    for _ in range(5):  # five wrong attempts are allowed
        assert client.post(url, {"pin": "0000"}).status_code == 200
    assert client.post(url, {"pin": "0000"}).status_code == 429  # sixth is blocked


def test_submission_is_rate_limited(client):
    _org, _customer, container, _st = _setup()
    _verify(client, container)
    url = reverse("portal:request", args=[container.qr_uid])
    for _ in range(3):  # three (invalid) submits pass the limiter
        assert client.post(url, {}).status_code == 200
    assert client.post(url, {}).status_code == 429  # fourth is blocked
