"""Tests for the web import flow (upload -> preview -> commit)."""

import pytest
import test_helpers
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from organizations.models import Membership
from containers.models import Customer

pytestmark = [pytest.mark.django_db]


def _login(client, role=Membership.Role.MEMBER):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    client.force_login(user)
    return user, org


def test_import_requires_member(client):
    _login(client, role=Membership.Role.VIEWER)
    assert client.get(reverse("containers:import")).status_code == 403


def test_import_shows_upload_form(client):
    _login(client)
    response = client.get(reverse("containers:import"))
    assert response.status_code == 200
    assert b"customers" in response.content  # entity option


def test_import_upload_preview_then_commit(client):
    _user, org = _login(client)
    url = reverse("containers:import")
    csv = SimpleUploadedFile(
        "c.csv", b"name,customer_number\nAcme,C1\nBeta,C2\n", content_type="text/csv"
    )
    upload = client.post(url, {"action": "upload", "entity": "customers", "file": csv})
    assert upload.status_code == 302
    # Preview is recomputed from the session on the next GET; nothing saved yet.
    preview = client.get(url)
    assert b"Acme" in preview.content
    assert Customer.objects.filter(organization=org).count() == 0
    # Confirm commits the rows.
    confirm = client.post(url, {"action": "confirm"})
    assert confirm.status_code == 302
    assert Customer.objects.filter(organization=org).count() == 2


def test_import_cancel_clears_pending(client):
    _user, org = _login(client)
    url = reverse("containers:import")
    csv = SimpleUploadedFile(
        "c.csv", b"name,customer_number\nAcme,C1\n", content_type="text/csv"
    )
    client.post(url, {"action": "upload", "entity": "customers", "file": csv})
    client.post(url, {"action": "cancel"})
    # After cancel the page is back to the upload form (no preview).
    assert b"Acme" not in client.get(url).content
    assert Customer.objects.filter(organization=org).count() == 0


def test_import_page_swedish(client):
    _login(client)
    response = client.get(reverse("containers:import"), HTTP_ACCEPT_LANGUAGE="sv")
    assert "Datatyp" in response.content.decode()  # "Data type"
