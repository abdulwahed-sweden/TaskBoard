
from rest_framework import permissions, viewsets

from organizations.models import Membership, Project
from organizations.permissions import has_role

from . import models
from . import serializers


class IsOrgMemberForWrites(permissions.IsAuthenticated):
    """Authenticated to read; object writes require ``member`` in the object's
    organization (so viewers are read-only). The viewset supplies the org via
    ``get_object_organization``."""

    def has_object_permission(self, request, view, obj):
        organization = view.get_object_organization(obj)
        if request.method in permissions.SAFE_METHODS:
            return has_role(request.user, organization, Membership.Role.VIEWER)
        return has_role(request.user, organization, Membership.Role.MEMBER)


class TaskViewSet(viewsets.ModelViewSet):
    """Tasks in projects within organizations the requesting user belongs to."""

    serializer_class = serializers.TaskSerializer
    permission_classes = [IsOrgMemberForWrites]

    def get_queryset(self):
        return models.Task.objects.filter(
            project__organization__members=self.request.user
        )

    def get_object_organization(self, obj):
        return obj.project.organization

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ProjectViewSet(viewsets.ModelViewSet):
    """Projects in organizations the requesting user belongs to."""

    serializer_class = serializers.ProjectSerializer
    permission_classes = [IsOrgMemberForWrites]

    def get_queryset(self):
        return Project.objects.filter(organization__members=self.request.user)

    def get_object_organization(self, obj):
        return obj.organization
