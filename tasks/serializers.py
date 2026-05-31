
from rest_framework import serializers

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
