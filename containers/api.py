"""DRF viewsets for the container operations API.

Every viewset is organization-scoped exactly like the tasks API: ``get_queryset``
filters to objects in organizations the requesting user belongs to (never
``.all()``), so foreign objects 404, and ``IsOrgMemberForWrites`` requires
``member`` to write and ``viewer`` to read. Status changes on a service request
go through the dedicated ``transition`` action so the workflow rules and activity
logging in the service layer are always applied.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from organizations.models import Membership
from organizations.permissions import has_role

from . import models, serializers
from .services import transition_service_request


class IsOrgMemberForWrites(permissions.IsAuthenticated):
    """Authenticated to read; object writes require ``member`` in the object's
    organization (viewers are read-only).

    A local copy of the tasks-app permission so the containers app stays
    decoupled from tasks; the view supplies the org via ``get_object_organization``.
    """

    def has_object_permission(self, request, view, obj):
        organization = view.get_object_organization(obj)
        if request.method in permissions.SAFE_METHODS:
            return has_role(request.user, organization, Membership.Role.VIEWER)
        return has_role(request.user, organization, Membership.Role.MEMBER)


class OrgScopedViewSet(viewsets.ModelViewSet):
    """Shared org scoping for every container resource."""

    permission_classes = [IsOrgMemberForWrites]

    def get_queryset(self):
        model = self.serializer_class.Meta.model
        if getattr(self, "swagger_fake_view", False):
            return model.objects.none()
        return model.objects.filter(organization__members=self.request.user)

    def get_object_organization(self, obj):
        return obj.organization


class CustomerViewSet(OrgScopedViewSet):
    serializer_class = serializers.CustomerSerializer
    filterset_fields = ["is_active"]
    ordering_fields = ["name", "created"]
    ordering = ["name"]
    search_fields = ["name", "customer_number", "org_number", "email"]


class SiteViewSet(OrgScopedViewSet):
    serializer_class = serializers.SiteSerializer
    filterset_fields = ["customer", "is_active", "city"]
    ordering_fields = ["city", "street", "created"]
    ordering = ["city", "street"]
    search_fields = ["label", "street", "city", "postal_code"]


class ContainerViewSet(OrgScopedViewSet):
    serializer_class = serializers.ContainerSerializer
    filterset_fields = ["customer", "site", "container_type", "waste_category", "status"]
    ordering_fields = ["created"]
    ordering = ["-created"]
    search_fields = ["serial_number", "qr_uid"]


class DriverViewSet(OrgScopedViewSet):
    serializer_class = serializers.DriverSerializer
    filterset_fields = ["is_active"]
    ordering_fields = ["name", "created"]
    ordering = ["name"]
    search_fields = ["name", "phone"]


class ServiceTypeViewSet(OrgScopedViewSet):
    serializer_class = serializers.ServiceTypeSerializer
    filterset_fields = ["category", "requires_pin", "is_active"]
    ordering_fields = ["name", "created"]
    ordering = ["name"]
    search_fields = ["name", "code"]


class ServiceRequestViewSet(OrgScopedViewSet):
    serializer_class = serializers.ServiceRequestSerializer
    filterset_fields = ["status", "priority", "source", "customer", "service_type"]
    ordering_fields = ["created", "scheduled_date", "requested_date", "reference"]
    ordering = ["-created"]
    search_fields = ["reference", "contact_name"]

    @extend_schema(
        request=serializers.TransitionSerializer,
        responses=serializers.ServiceRequestSerializer,
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        """Move a request to a new status through the workflow rules.

        Object-level permission (member+) and org scoping are enforced by
        ``get_object``; the role/transition/note rules and activity logging come
        from ``transition_service_request``. A disallowed move returns 400.
        """
        service_request = self.get_object()
        input_serializer = serializers.TransitionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            transition_service_request(
                service_request,
                input_serializer.validated_data["to_status"],
                user=request.user,
                note=input_serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST
            )
        service_request.refresh_from_db()
        return Response(self.get_serializer(service_request).data)


class AssignmentViewSet(OrgScopedViewSet):
    serializer_class = serializers.AssignmentSerializer
    filterset_fields = ["driver", "service_request", "status"]
    ordering_fields = ["scheduled_date", "sequence", "created"]
    ordering = ["sequence", "id"]
    search_fields = ["service_request__reference", "driver__name"]
