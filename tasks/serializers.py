
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from organizations.custom_fields import validate_custom_fields
from organizations.models import Membership, Project
from organizations.permissions import has_role

from . import models


class TaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Task
        fields = [
            "id",
            "created",
            "last_updated",
            "title",
            "notes",
            "is_done",
            "due_date",
            "owner",
            "project",
            "custom_fields",
        ]
        read_only_fields = ["created", "last_updated", "owner"]

    def validate_project(self, project):
        """A task may only be filed into a project in an org the requesting
        user can write to (member or above)."""
        user = self.context["request"].user
        if not has_role(user, project.organization, Membership.Role.MEMBER):
            raise serializers.ValidationError(
                "You do not have permission to use this project."
            )
        return project

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Only (re)validate custom fields when the project or the fields change.
        if "project" not in attrs and "custom_fields" not in attrs:
            return attrs
        project = attrs.get("project") or getattr(self.instance, "project", None)
        project_type = (
            project.project_type
            if project and project.project_type_id
            else None
        )
        raw = (
            attrs["custom_fields"]
            if "custom_fields" in attrs
            else getattr(self.instance, "custom_fields", {})
        )
        try:
            attrs["custom_fields"] = validate_custom_fields(project_type, raw or {})
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"custom_fields": exc.message_dict})
        return attrs


class ProjectSerializer(serializers.ModelSerializer):

    class Meta:
        model = Project
        fields = ["id", "organization", "name", "description", "created"]
        read_only_fields = ["created"]

    def validate_organization(self, organization):
        user = self.context["request"].user
        if not has_role(user, organization, Membership.Role.MEMBER):
            raise serializers.ValidationError(
                "You do not have permission to use this organization."
            )
        return organization
