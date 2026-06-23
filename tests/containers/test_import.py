"""Tests for the container-domain CSV/XLSX importers and management command."""

import io

import pytest
import test_helpers
from django.core.management import call_command
from django.core.management.base import CommandError

from containers.importer import (
    ContainerImporter,
    CustomerImporter,
    ServiceRequestImporter,
    SiteImporter,
)
from containers.models import Container, Customer, ServiceRequest, Site

pytestmark = [pytest.mark.django_db]


def _rows(importer, headers, rows):
    mapping = importer.auto_mapping(headers)
    return importer, mapping


# --- customers ---------------------------------------------------------------

def test_customer_import_creates_and_validates():
    org = test_helpers.create_organizations_Organization()
    importer = CustomerImporter(org)
    headers = ["name", "customer_number", "email"]
    rows = [
        {"name": "Acme AB", "customer_number": "C1", "email": "ok@example.com"},
        {"name": "", "customer_number": "C2", "email": "ok@example.com"},   # missing name
        {"name": "Bad Email", "customer_number": "C3", "email": "nope"},    # bad email
    ]
    result = importer.commit(rows, importer.auto_mapping(headers))
    assert result["created"] == 1
    assert {s["row_number"] for s in result["skipped"]} == {2, 3}
    assert Customer.objects.filter(organization=org).count() == 1


def test_customer_import_detects_duplicates():
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_Customer(organization=org, customer_number="DUP")
    importer = CustomerImporter(org)
    headers = ["name", "customer_number"]
    rows = [{"name": "Again", "customer_number": "DUP"}]
    result = importer.commit(rows, importer.auto_mapping(headers))
    assert result["created"] == 0
    assert result["skipped"][0]["row_number"] == 1


# --- sites (FK resolution) ---------------------------------------------------

def test_site_import_resolves_customer_by_number():
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_Customer(organization=org, customer_number="C1")
    importer = SiteImporter(org)
    headers = ["customer_number", "street", "city", "label"]
    rows = [
        {"customer_number": "C1", "street": "Main 1", "city": "Stockholm", "label": "Yard"},
        {"customer_number": "NOPE", "street": "X 2", "city": "Y", "label": "Z"},
    ]
    result = importer.commit(rows, importer.auto_mapping(headers))
    assert result["created"] == 1
    assert result["skipped"][0]["row_number"] == 2
    assert "customer_number" in result["skipped"][0]["errors"]
    assert Site.objects.filter(organization=org).count() == 1


# --- containers (choices, pin, qr) ------------------------------------------

def test_container_import_type_validation_and_pin():
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_Customer(organization=org, customer_number="C1")
    importer = ContainerImporter(org)
    headers = ["customer_number", "container_type", "size", "pin"]
    rows = [
        {"customer_number": "C1", "container_type": "skip", "size": "10 m3", "pin": "2468"},
        {"customer_number": "C1", "container_type": "spaceship", "size": "", "pin": ""},
    ]
    result = importer.commit(rows, importer.auto_mapping(headers))
    assert result["created"] == 1
    assert "container_type" in result["skipped"][0]["errors"]
    container = Container.objects.get(organization=org)
    assert container.qr_uid  # auto-generated
    assert container.pin_hash and container.pin_hash != "2468"  # hashed, not raw


# --- service requests --------------------------------------------------------

def test_service_request_import_resolves_type_and_defaults():
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_Customer(organization=org, customer_number="C1")
    test_helpers.create_containers_ServiceType(organization=org, code="emptying")
    importer = ServiceRequestImporter(org)
    headers = ["customer_number", "service_type_code", "requested_date", "priority"]
    rows = [
        {"customer_number": "C1", "service_type_code": "emptying",
         "requested_date": "2026-07-01", "priority": "high"},
        {"customer_number": "C1", "service_type_code": "ghost",
         "requested_date": "not-a-date", "priority": "urgent"},
    ]
    result = importer.commit(rows, importer.auto_mapping(headers))
    assert result["created"] == 1
    errs = result["skipped"][0]["errors"]
    assert {"service_type_code", "requested_date", "priority"} <= set(errs)
    sr = ServiceRequest.objects.get(organization=org)
    assert sr.source == ServiceRequest.Source.IMPORT
    assert sr.status == ServiceRequest.Status.NEW
    assert sr.priority == "high"
    assert sr.reference  # auto-generated when blank


# --- management command ------------------------------------------------------

def _csv_file(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_command_dry_run_writes_nothing(tmp_path, capsys):
    org = test_helpers.create_organizations_Organization()
    path = _csv_file(tmp_path, "c.csv", "name,customer_number\nAcme,C1\n")
    call_command("import_containers", "customers", "--org", org.slug, "--file", path)
    assert Customer.objects.filter(organization=org).count() == 0  # dry run


def test_command_commit_creates_rows(tmp_path):
    org = test_helpers.create_organizations_Organization()
    path = _csv_file(tmp_path, "c.csv", "name,customer_number\nAcme,C1\nBeta,C2\n")
    call_command(
        "import_containers", "customers", "--org", org.slug, "--file", path, "--commit"
    )
    assert Customer.objects.filter(organization=org).count() == 2


def test_command_unknown_org_raises(tmp_path):
    path = _csv_file(tmp_path, "c.csv", "name,customer_number\nAcme,C1\n")
    with pytest.raises(CommandError):
        call_command("import_containers", "customers", "--org", "ghost", "--file", path)
