from django.db import models
from django.urls import reverse


class Task(models.Model):

    owner = models.ForeignKey("auth.User", null=True, on_delete=models.CASCADE)
    project = models.ForeignKey(
        "organizations.Project", on_delete=models.CASCADE, related_name="tasks"
    )

    # Fields
    created = models.DateTimeField(auto_now_add=True, editable=False)
    last_updated = models.DateTimeField(auto_now=True, editable=False)
    title = models.CharField(max_length=120)
    notes = models.TextField(blank=True, default='')
    is_done = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    # Domain-specific data validated against the project's type schema.
    custom_fields = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.title

    def clean(self):
        """Validate custom fields against the project's type so model-level
        saves (e.g. the admin) stay consistent with the form and API.

        ``TaskForm`` validates custom fields itself and sets
        ``_skip_custom_field_validation`` to avoid double validation (it maps
        errors onto its per-field widgets); here errors are attached to the
        ``custom_fields`` field for the admin / raw-JSON path.
        """
        from django.core.exceptions import ValidationError

        from organizations.custom_fields import validate_custom_fields

        if getattr(self, "_skip_custom_field_validation", False):
            return
        project_type = self.project.project_type if self.project_id else None
        try:
            self.custom_fields = validate_custom_fields(
                project_type, self.custom_fields
            )
        except ValidationError as exc:
            raise ValidationError({"custom_fields": exc.messages})

    @staticmethod
    def get_create_url():
        return reverse("tasks:Task_create")

    def get_absolute_url(self):
        return reverse("tasks:Task_detail", args=(self.pk,))

    def get_update_url(self):
        return reverse("tasks:Task_update", args=(self.pk,))

    def get_delete_url(self):
        return reverse("tasks:Task_delete", args=(self.pk,))



