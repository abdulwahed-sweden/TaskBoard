"""Step 2 of 3: give every task a project.

Create a default "General" project in each organization, then attach each task
to the General project of its owner's personal org (the org where the owner
holds the ``owner`` role, created in organizations migration 0002). Tasks with
no owner — or whose owner has no membership — go to a lazily-created, memberless
"Unassigned" organization. Such tasks were already invisible under owner-scoping
(``owner=user`` never matched a null owner), and a memberless org keeps them
invisible under the new membership-scoping, so behavior is preserved with no
data lost.
"""

from django.db import migrations

GENERAL = "General"
UNASSIGNED_ORG = "Unassigned"


def _general_project(Project, organization):
    project, _ = Project.objects.get_or_create(
        organization=organization, name=GENERAL
    )
    return project


def populate_projects(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Membership = apps.get_model("organizations", "Membership")
    Project = apps.get_model("organizations", "Project")
    Task = apps.get_model("tasks", "Task")

    # A General project for every existing organization.
    for organization in Organization.objects.all():
        _general_project(Project, organization)

    fallback_org = None
    for task in Task.objects.filter(project__isnull=True):
        organization = None
        if task.owner_id is not None:
            owner_membership = (
                Membership.objects.filter(user_id=task.owner_id, role="owner")
                .select_related("organization")
                .first()
            )
            if owner_membership is not None:
                organization = owner_membership.organization
        if organization is None:
            if fallback_org is None:
                fallback_org, _ = Organization.objects.get_or_create(
                    slug="unassigned", defaults={"name": UNASSIGNED_ORG}
                )
            organization = fallback_org
        task.project = _general_project(Project, organization)
        task.save(update_fields=["project"])


def detach_projects(apps, schema_editor):
    # Reverse: drop the General projects this migration relies on. Tasks lose
    # their project (the column is nullable again after 0004 is reversed first).
    Project = apps.get_model("organizations", "Project")
    Project.objects.filter(name=GENERAL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0002_task_project_nullable"),
    ]

    operations = [
        migrations.RunPython(populate_projects, detach_projects),
    ]
