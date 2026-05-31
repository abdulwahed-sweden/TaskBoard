import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Step 3 of 3: now that every task has a project, make the FK required."""

    dependencies = [
        ("tasks", "0003_populate_projects"),
    ]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to="organizations.project",
            ),
        ),
    ]
