from django.db import models
from django.urls import reverse


class Organization(models.Model):
    """A tenant. Work (projects, tasks) belongs to an organization, and users
    reach it through a :class:`Membership`."""

    name = models.CharField(max_length=120)
    # Stable handle for URLs and the org switcher; generated from the name.
    slug = models.SlugField(max_length=140, unique=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)
    members = models.ManyToManyField(
        "auth.User",
        through="Membership",
        related_name="organizations",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProjectType(models.Model):
    """A reusable work template: declares the custom-field schema (and, later,
    workflow) that projects of this type share."""

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FieldDefinition(models.Model):
    """One custom field declared by a :class:`ProjectType`. The set of
    definitions for a type is the schema that ``Task.custom_fields`` is
    validated against."""

    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        CHOICE = "choice", "Choice"
        BOOLEAN = "boolean", "Boolean"

    project_type = models.ForeignKey(
        ProjectType, on_delete=models.CASCADE, related_name="field_definitions"
    )
    name = models.SlugField(max_length=60)  # the key used in custom_fields
    label = models.CharField(max_length=120)
    field_type = models.CharField(max_length=20, choices=FieldType.choices)
    required = models.BooleanField(default=False)
    # Only meaningful when field_type == CHOICE: the allowed values.
    choices = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project_type", "name"],
                name="unique_field_name_per_project_type",
            )
        ]

    def __str__(self):
        return f"{self.project_type}.{self.name}"


class StatusDefinition(models.Model):
    """One status in a :class:`ProjectType`'s workflow. The ordered set of
    definitions is the workflow a typed task's ``status`` must belong to."""

    project_type = models.ForeignKey(
        ProjectType, on_delete=models.CASCADE, related_name="status_definitions"
    )
    name = models.SlugField(max_length=60)  # the value stored in Task.status
    label = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)  # status for new tasks
    is_terminal = models.BooleanField(default=False)  # drives Task.is_done

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project_type", "name"],
                name="unique_status_name_per_project_type",
            )
        ]

    def __str__(self):
        return f"{self.project_type}:{self.name}"


class Project(models.Model):
    """A container for work (tasks) inside an organization."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="projects"
    )
    project_type = models.ForeignKey(
        ProjectType,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_project_name_per_organization",
            )
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("organizations:Project_detail", args=(self.pk,))


class Membership(models.Model):
    """Links a user to an organization with a role."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.MEMBER
    )
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["organization", "user"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="unique_user_per_organization",
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"


# Role precedence, highest first. Used by the permission helpers to answer
# "does this membership satisfy at least <min_role>?".
ROLE_RANK = {
    Membership.Role.OWNER: 4,
    Membership.Role.ADMIN: 3,
    Membership.Role.MEMBER: 2,
    Membership.Role.VIEWER: 1,
}


def role_rank(role):
    """Numeric precedence for a role value (unknown roles rank 0)."""
    return ROLE_RANK.get(role, 0)
