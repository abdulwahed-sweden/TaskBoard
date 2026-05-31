"""Seed status workflows for the two seeded project types.

Idempotent (get_or_create) and self-contained (historical models). Each list is
ordered; the first entry is the default and the last is terminal (drives
Task.is_done).
"""

from django.db import migrations

WORKFLOWS = {
    "Software Tasks": [
        ("backlog", "Backlog"),
        ("in_progress", "In Progress"),
        ("in_review", "In Review"),
        ("done", "Done"),
    ],
    "Translation Jobs": [
        ("new", "New"),
        ("translating", "Translating"),
        ("review", "Review"),
        ("delivered", "Delivered"),
    ],
}


def seed_workflows(apps, schema_editor):
    ProjectType = apps.get_model("organizations", "ProjectType")
    StatusDefinition = apps.get_model("organizations", "StatusDefinition")
    for type_name, statuses in WORKFLOWS.items():
        try:
            project_type = ProjectType.objects.get(name=type_name)
        except ProjectType.DoesNotExist:
            continue
        last = len(statuses) - 1
        for order, (name, label) in enumerate(statuses):
            StatusDefinition.objects.get_or_create(
                project_type=project_type,
                name=name,
                defaults={
                    "label": label,
                    "order": order,
                    "is_default": order == 0,
                    "is_terminal": order == last,
                },
            )


def unseed_workflows(apps, schema_editor):
    ProjectType = apps.get_model("organizations", "ProjectType")
    StatusDefinition = apps.get_model("organizations", "StatusDefinition")
    StatusDefinition.objects.filter(
        project_type__name__in=WORKFLOWS
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0006_statusdefinition"),
        ("organizations", "0005_seed_project_types"),
    ]

    operations = [
        migrations.RunPython(seed_workflows, unseed_workflows),
    ]
