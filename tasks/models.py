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
    # Workflow status, validated against the project type's status definitions.
    # Empty for projects whose type has no workflow (is_done is used directly).
    status = models.CharField(max_length=60, blank=True, default='')
    due_date = models.DateField(null=True, blank=True)
    # Domain-specific data validated against the project's type schema.
    custom_fields = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.title

    @property
    def status_label(self):
        """Human label for the current status (falls back to the raw value)."""
        if not self.status or not self.project_id:
            return self.status
        project_type = self.project.project_type
        if project_type is None:
            return self.status
        definition = project_type.status_definitions.filter(
            name=self.status
        ).first()
        return definition.label if definition else self.status

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
        from organizations.workflow import validate_status

        if getattr(self, "_skip_custom_field_validation", False):
            return
        project_type = self.project.project_type if self.project_id else None
        try:
            self.custom_fields = validate_custom_fields(
                project_type, self.custom_fields
            )
        except ValidationError as exc:
            raise ValidationError({"custom_fields": exc.messages})
        try:
            self.status = validate_status(project_type, self.status)
        except ValidationError as exc:
            raise ValidationError({"status": exc.messages})

    def save(self, *args, **kwargs):
        """Keep is_done in sync with status on every write path: a typed task's
        completion flag is derived from whether its status is terminal; untyped
        tasks keep is_done as set directly."""
        from organizations.workflow import is_terminal_status

        if self.project_id:
            project_type = self.project.project_type
            if project_type is not None and project_type.status_definitions.exists():
                self.is_done = is_terminal_status(project_type, self.status)
        super().save(*args, **kwargs)

    @staticmethod
    def get_create_url():
        return reverse("tasks:Task_create")

    def get_absolute_url(self):
        return reverse("tasks:Task_detail", args=(self.pk,))

    def get_update_url(self):
        return reverse("tasks:Task_update", args=(self.pk,))

    def get_delete_url(self):
        return reverse("tasks:Task_delete", args=(self.pk,))


class Comment(models.Model):
    """A discussion message on a task, by a project member."""

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        "auth.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = models.TextField()
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["created"]

    def __str__(self):
        return f"Comment by {self.author} on {self.task}"


class Activity(models.Model):
    """Append-only record of a task lifecycle event. There are no edit/delete
    paths — entries are only ever created (see tasks/activity.py)."""

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        STATUS_CHANGED = "status_changed", "Status changed"
        ASSIGNED = "assigned", "Assigned"

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name="activities"
    )
    actor = models.ForeignKey(
        "auth.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    description = models.CharField(max_length=255)
    detail = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name_plural = "activities"

    def __str__(self):
        return self.description



