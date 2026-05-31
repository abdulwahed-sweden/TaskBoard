"""Seed the two starter project types and their field schemas.

Idempotent (uses get_or_create) and self-contained (historical models). Mirrors
the field-type values in ``FieldDefinition.FieldType``.
"""

from django.db import migrations

SEED = {
    "Software Tasks": [
        {
            "name": "priority",
            "label": "Priority",
            "field_type": "choice",
            "required": True,
            "choices": ["Low", "Medium", "High"],
            "order": 1,
        },
        {
            "name": "component",
            "label": "Component",
            "field_type": "text",
            "required": False,
            "order": 2,
        },
    ],
    "Translation Jobs": [
        {
            "name": "source_lang",
            "label": "Source language",
            "field_type": "text",
            "required": True,
            "order": 1,
        },
        {
            "name": "target_lang",
            "label": "Target language",
            "field_type": "text",
            "required": True,
            "order": 2,
        },
        {
            "name": "word_count",
            "label": "Word count",
            "field_type": "number",
            "required": False,
            "order": 3,
        },
        {
            "name": "deadline",
            "label": "Deadline",
            "field_type": "date",
            "required": False,
            "order": 4,
        },
    ],
}


def seed_project_types(apps, schema_editor):
    ProjectType = apps.get_model("organizations", "ProjectType")
    FieldDefinition = apps.get_model("organizations", "FieldDefinition")
    for type_name, fields in SEED.items():
        project_type, _ = ProjectType.objects.get_or_create(name=type_name)
        for field in fields:
            FieldDefinition.objects.get_or_create(
                project_type=project_type,
                name=field["name"],
                defaults={
                    "label": field["label"],
                    "field_type": field["field_type"],
                    "required": field["required"],
                    "choices": field.get("choices", []),
                    "order": field["order"],
                },
            )


def unseed_project_types(apps, schema_editor):
    ProjectType = apps.get_model("organizations", "ProjectType")
    # PROTECT on Project.project_type means this errors if a project still uses
    # a seeded type — intentional, so we don't orphan typed projects.
    ProjectType.objects.filter(name__in=SEED).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0004_projecttype_project_project_type_fielddefinition"),
    ]

    operations = [
        migrations.RunPython(seed_project_types, unseed_project_types),
    ]
