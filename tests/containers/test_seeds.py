"""Tests for the ServiceType seed catalog, service, and management command."""

import pytest
import test_helpers
from django.core.management import call_command
from django.core.management.base import CommandError

from containers.models import ServiceType
from containers.services import STANDARD_SERVICE_TYPES, seed_service_types

pytestmark = [pytest.mark.django_db]

STANDARD_COUNT = len(STANDARD_SERVICE_TYPES)


def test_seed_creates_standard_types():
    org = test_helpers.create_organizations_Organization()
    created = seed_service_types(org)
    assert len(created) == STANDARD_COUNT
    assert ServiceType.objects.filter(organization=org).count() == STANDARD_COUNT
    codes = set(
        ServiceType.objects.filter(organization=org).values_list("code", flat=True)
    )
    assert {"emptying", "asbestos", "quote_request"} <= codes


def test_seed_is_idempotent():
    org = test_helpers.create_organizations_Organization()
    seed_service_types(org)
    created_again = seed_service_types(org)
    assert created_again == []
    assert ServiceType.objects.filter(organization=org).count() == STANDARD_COUNT


def test_seed_is_organization_scoped():
    org_a = test_helpers.create_organizations_Organization()
    org_b = test_helpers.create_organizations_Organization()
    seed_service_types(org_a)
    assert ServiceType.objects.filter(organization=org_b).count() == 0
    seed_service_types(org_b)
    assert ServiceType.objects.filter(organization=org_a).count() == STANDARD_COUNT
    assert ServiceType.objects.filter(organization=org_b).count() == STANDARD_COUNT


def test_management_command_for_single_org():
    org = test_helpers.create_organizations_Organization()
    call_command("seed_service_types", "--org", org.slug)
    assert ServiceType.objects.filter(organization=org).count() == STANDARD_COUNT


def test_management_command_for_all_orgs():
    org_a = test_helpers.create_organizations_Organization()
    org_b = test_helpers.create_organizations_Organization()
    call_command("seed_service_types", "--all")
    assert ServiceType.objects.filter(organization=org_a).count() == STANDARD_COUNT
    assert ServiceType.objects.filter(organization=org_b).count() == STANDARD_COUNT


def test_management_command_unknown_org_raises():
    with pytest.raises(CommandError):
        call_command("seed_service_types", "--org", "does-not-exist")
