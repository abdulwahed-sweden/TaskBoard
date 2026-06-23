"""Model tests for the new container operations domain (first slice).

Covers creation, organization scoping, the customer/site/container and
assignment relationships, service-request creation, and per-organization
uniqueness. Behaviour reused from the configurable engine arrives in later
phases and is tested then.
"""

import pytest
import test_helpers
from django.db import IntegrityError

from containers.models import (
    Assignment,
    Container,
    Customer,
    Driver,
    ServiceRequest,
    ServiceType,
    Site,
)

pytestmark = [pytest.mark.django_db]


# --- creation ----------------------------------------------------------------

def test_create_all_models():
    customer = test_helpers.create_containers_Customer()
    site = test_helpers.create_containers_Site(customer=customer)
    container = test_helpers.create_containers_Container(customer=customer, site=site)
    driver = test_helpers.create_containers_Driver(organization=customer.organization)
    service_type = test_helpers.create_containers_ServiceType(
        organization=customer.organization
    )
    request = test_helpers.create_containers_ServiceRequest(
        customer=customer, site=site, container=container, service_type=service_type
    )
    assignment = test_helpers.create_containers_Assignment(
        service_request=request, driver=driver
    )

    assert Customer.objects.count() == 1
    assert Site.objects.count() == 1
    assert Container.objects.count() == 1
    assert Driver.objects.count() == 1
    assert ServiceType.objects.count() == 1
    assert ServiceRequest.objects.count() == 1
    assert Assignment.objects.count() == 1


def test_container_qr_uid_is_generated_and_unique():
    a = test_helpers.create_containers_Container()
    b = test_helpers.create_containers_Container()
    assert a.qr_uid and b.qr_uid
    assert a.qr_uid != b.qr_uid


def test_service_request_defaults():
    request = test_helpers.create_containers_ServiceRequest()
    assert request.source == ServiceRequest.Source.PORTAL
    assert request.priority == ServiceRequest.Priority.NORMAL
    assert request.status == ServiceRequest.Status.NEW
    assert request.custom_fields == {}


# --- organization scoping ----------------------------------------------------

def test_models_are_organization_scoped():
    org_a = test_helpers.create_organizations_Organization()
    org_b = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_Customer(organization=org_a)
    test_helpers.create_containers_Customer(organization=org_b)
    test_helpers.create_containers_Customer(organization=org_b)

    assert Customer.objects.filter(organization=org_a).count() == 1
    assert Customer.objects.filter(organization=org_b).count() == 2
    # Reverse accessor from the existing Organization model.
    assert org_a.customers.count() == 1
    assert org_b.customers.count() == 2


# --- relationships -----------------------------------------------------------

def test_customer_site_container_relationships():
    customer = test_helpers.create_containers_Customer()
    site = test_helpers.create_containers_Site(customer=customer)
    container = test_helpers.create_containers_Container(customer=customer, site=site)

    assert site.customer == customer
    assert container.customer == customer
    assert container.site == site
    # Reverse accessors.
    assert customer.sites.first() == site
    assert customer.containers.first() == container
    assert site.containers.first() == container


def test_assignment_relationships():
    request = test_helpers.create_containers_ServiceRequest()
    driver = test_helpers.create_containers_Driver(
        organization=request.organization
    )
    assignment = test_helpers.create_containers_Assignment(
        service_request=request, driver=driver
    )

    assert assignment.service_request == request
    assert assignment.driver == driver
    assert request.assignments.first() == assignment
    assert driver.assignments.first() == assignment


def test_service_request_optional_links_may_be_blank():
    # A quote request can exist without a site or container.
    request = test_helpers.create_containers_ServiceRequest(site=None, container=None)
    assert request.site is None
    assert request.container is None
    assert request.customer is not None
    assert request.service_type is not None


# --- per-organization uniqueness ---------------------------------------------

def test_customer_number_unique_within_organization():
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_Customer(organization=org, customer_number="DUP")
    with pytest.raises(IntegrityError):
        test_helpers.create_containers_Customer(
            organization=org, customer_number="DUP"
        )


def test_customer_number_may_repeat_across_organizations():
    org_a = test_helpers.create_organizations_Organization()
    org_b = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_Customer(organization=org_a, customer_number="SAME")
    # Same number, different tenant — allowed.
    test_helpers.create_containers_Customer(organization=org_b, customer_number="SAME")
    assert Customer.objects.filter(customer_number="SAME").count() == 2


def test_service_request_reference_unique_within_organization():
    org = test_helpers.create_organizations_Organization()
    service_type = test_helpers.create_containers_ServiceType(organization=org)
    customer = test_helpers.create_containers_Customer(organization=org)
    test_helpers.create_containers_ServiceRequest(
        organization=org, customer=customer, service_type=service_type, reference="SR-1"
    )
    with pytest.raises(IntegrityError):
        test_helpers.create_containers_ServiceRequest(
            organization=org,
            customer=customer,
            service_type=service_type,
            reference="SR-1",
        )


def test_service_type_code_unique_within_organization():
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_containers_ServiceType(organization=org, code="emptying")
    with pytest.raises(IntegrityError):
        test_helpers.create_containers_ServiceType(organization=org, code="emptying")
