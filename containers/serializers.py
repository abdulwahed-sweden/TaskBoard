"""DRF serializers for the container operations API.

Mirrors the hardening in ``tasks/serializers.py``: writes are gated on holding
``member`` in the target organization, and tenant integrity is enforced — every
related object referenced on a write must belong to the same organization as the
record, so a member of one tenant cannot wire in another tenant's data.
"""

from rest_framework import serializers

from organizations.models import Membership
from organizations.permissions import has_role

from . import models


def _require_org_write(user, organization):
    if not has_role(user, organization, Membership.Role.MEMBER):
        raise serializers.ValidationError(
            "You do not have permission to use this organization."
        )


class OrgScopedSerializer(serializers.ModelSerializer):
    """Base serializer enforcing organization write permission and that the FK
    fields named in ``same_org_fields`` share the record's organization."""

    # FK field names that must point at objects in the same organization.
    same_org_fields = ()

    def validate_organization(self, organization):
        _require_org_write(self.context["request"].user, organization)
        return organization

    def _resolve(self, attrs, field):
        if field in attrs:
            return attrs[field]
        return getattr(self.instance, field, None) if self.instance else None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        organization = attrs.get("organization") or getattr(
            self.instance, "organization", None
        )
        if organization is not None:
            errors = {}
            for field in self.same_org_fields:
                obj = self._resolve(attrs, field)
                if obj is not None and getattr(obj, "organization_id", None) != organization.id:
                    errors[field] = "Must belong to the same organization."
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class CustomerSerializer(OrgScopedSerializer):
    class Meta:
        model = models.Customer
        fields = [
            "id", "organization", "name", "customer_number", "org_number",
            "email", "phone", "billing_address", "notes", "is_active", "created",
        ]
        read_only_fields = ["created"]


class SiteSerializer(OrgScopedSerializer):
    same_org_fields = ("customer",)

    class Meta:
        model = models.Site
        fields = [
            "id", "organization", "customer", "label", "street", "postal_code",
            "city", "municipality", "access_notes", "is_active", "created",
        ]
        read_only_fields = ["created"]


class ContainerSerializer(OrgScopedSerializer):
    same_org_fields = ("customer", "site")

    class Meta:
        model = models.Container
        # pin_hash is intentionally excluded — never read or written via the API.
        fields = [
            "id", "organization", "customer", "site", "qr_uid", "container_type",
            "size", "serial_number", "waste_category", "status", "placed_at",
            "notes", "created",
        ]
        read_only_fields = ["qr_uid", "created"]


class DriverSerializer(OrgScopedSerializer):
    class Meta:
        model = models.Driver
        fields = [
            "id", "organization", "user", "name", "phone", "email",
            "license_class", "is_active", "created",
        ]
        read_only_fields = ["created"]


class ServiceTypeSerializer(OrgScopedSerializer):
    class Meta:
        model = models.ServiceType
        fields = [
            "id", "organization", "project_type", "code", "name", "category",
            "requires_pin", "default_sla_days", "is_active", "created",
        ]
        read_only_fields = ["created"]


class ServiceRequestSerializer(OrgScopedSerializer):
    same_org_fields = ("customer", "site", "container", "service_type")

    class Meta:
        model = models.ServiceRequest
        fields = [
            "id", "organization", "customer", "site", "container", "service_type",
            "reference", "source", "status", "priority", "owner",
            "requested_date", "scheduled_date", "contact_name", "contact_phone",
            "notes", "custom_fields", "created", "updated",
        ]
        # status changes only through the workflow transition action.
        read_only_fields = ["status", "created", "updated"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        organization = attrs.get("organization") or getattr(
            self.instance, "organization", None
        )
        owner = self._resolve(attrs, "owner")
        if owner is not None and organization is not None:
            if not Membership.objects.filter(
                user=owner, organization=organization
            ).exists():
                raise serializers.ValidationError(
                    {"owner": "Assignee must be a member of the organization."}
                )
        return attrs


class AssignmentSerializer(OrgScopedSerializer):
    same_org_fields = ("service_request", "driver")

    class Meta:
        model = models.Assignment
        fields = [
            "id", "organization", "service_request", "driver", "scheduled_date",
            "sequence", "status", "notes", "created",
        ]
        read_only_fields = ["created"]


class TransitionSerializer(serializers.Serializer):
    """Input for the ServiceRequest status-transition action."""

    to_status = serializers.ChoiceField(
        choices=models.ServiceRequest.Status.choices
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")
