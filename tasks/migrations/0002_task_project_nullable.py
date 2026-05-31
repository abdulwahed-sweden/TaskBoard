import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Step 1 of 3: add the project FK as nullable so existing rows survive.

    The data migration (0003) backfills it and 0004 makes it required.
    """

    dependencies = [
        ("tasks", "0001_initial"),
        ("organizations", "0003_project"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="project",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to="organizations.project",
            ),
        ),
    ]
