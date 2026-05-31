
from rest_framework import permissions, viewsets

from organizations.models import Membership, Project
from organizations.permissions import has_role

from . import models
from . import serializers
from .activity import log_changes, log_created, snapshot


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
    queryset = models.Task.objects.none()  # lets the schema introspect the model
    # Filters/search/ordering only ever narrow the already org-scoped queryset.
    filterset_fields = ["project", "is_done", "status"]
    ordering_fields = ["created", "due_date", "title"]
    ordering = ["-created"]
    search_fields = ["title", "notes"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return models.Task.objects.none()
        return models.Task.objects.filter(
            project__organization__members=self.request.user
        )

    def get_object_organization(self, obj):
        return obj.project.organization

    def perform_create(self, serializer):
        # Default the assignee to the requesting user when none was supplied.
        extra = {}
        if not serializer.validated_data.get("owner"):
            extra["owner"] = self.request.user
        task = serializer.save(**extra)
        log_created(task, self.request.user)

    def perform_update(self, serializer):
        previous = snapshot(serializer.instance)
        task = serializer.save()
        log_changes(task, self.request.user, previous)


class ProjectViewSet(viewsets.ModelViewSet):
    """Projects in organizations the requesting user belongs to."""

    serializer_class = serializers.ProjectSerializer
    permission_classes = [IsOrgMemberForWrites]
    queryset = Project.objects.none()  # lets the schema introspect the model
    filterset_fields = ["organization"]
    ordering_fields = ["name", "created"]
    ordering = ["name"]
    search_fields = ["name"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Project.objects.none()
        return Project.objects.filter(organization__members=self.request.user)

    def get_object_organization(self, obj):
        return obj.organization
