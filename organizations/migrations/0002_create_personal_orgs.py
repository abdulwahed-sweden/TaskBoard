"""Give every pre-existing user a personal organization they own.

Phase 1 only establishes tenancy. Existing tasks stay owner-scoped and are not
moved here; attaching tasks to an org/project is handled by the Phase 2
migration once the ``Task -> Project -> Organization`` links exist.

Slug/role logic mirrors ``organizations.services.create_personal_organization``;
it is duplicated rather than imported because data migrations must use the
historical models supplied via ``apps``.
"""

from django.db import migrations
from django.utils.text import slugify


def _unique_slug(Organization, base):
    root = slugify(base) or "org"
    candidate = root
    suffix = 2
    while Organization.objects.filter(slug=candidate).exists():
        candidate = f"{root}-{suffix}"
        suffix += 1
    return candidate


def create_personal_orgs(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Organization = apps.get_model("organizations", "Organization")
    Membership = apps.get_model("organizations", "Membership")

    for user in User.objects.all():
        # Skip users who somehow already own an org (idempotent re-runs).
        if Membership.objects.filter(user=user, role="owner").exists():
            continue
        organization = Organization.objects.create(
            name=f"{user.username}'s Organization",
            slug=_unique_slug(Organization, user.username),
        )
        Membership.objects.create(
            user=user, organization=organization, role="owner"
        )


def remove_personal_orgs(apps, schema_editor):
    # Reverse by dropping the owner memberships and their now-empty orgs.
    Organization = apps.get_model("organizations", "Organization")
    Membership = apps.get_model("organizations", "Membership")
    owner_org_ids = list(
        Membership.objects.filter(role="owner").values_list(
            "organization_id", flat=True
        )
    )
    Membership.objects.filter(organization_id__in=owner_org_ids).delete()
    Organization.objects.filter(id__in=owner_org_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_personal_orgs, remove_personal_orgs),
    ]
