from django.db import models


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
