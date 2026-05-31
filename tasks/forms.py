
from django import forms
from django.core.exceptions import ValidationError

from organizations.custom_fields import validate_custom_fields
from organizations.models import FieldDefinition, Project

from . import models

CUSTOM_PREFIX = "custom_"


class TaskForm(forms.ModelForm):
    class Meta:
        model = models.Task
        fields = [
            "project",
            "title",
            "notes",
            "is_done",
            "due_date",
        ]

    def __init__(self, *args, projects=None, **kwargs):
        """``projects`` limits the selectable projects. Custom fields are added
        dynamically from the (bound or instance) project's type schema."""
        super().__init__(*args, **kwargs)
        if projects is not None:
            self.fields["project"].queryset = projects
        # This form validates custom fields onto its per-field widgets, so tell
        # the model to skip its own (raw-keyed) custom-field validation.
        self.instance._skip_custom_field_validation = True
        self._custom_definitions = {}
        self._build_custom_fields(self._resolve_project())

    # -- dynamic custom fields ------------------------------------------------

    def _resolve_project(self):
        """The project whose schema drives the custom fields: the submitted one
        when bound, otherwise the instance/initial project."""
        if self.is_bound:
            project_id = self.data.get("project")
        else:
            project_id = self.initial.get("project") or self.instance.project_id
        if not project_id:
            return None
        return (
            Project.objects.filter(pk=project_id)
            .select_related("project_type")
            .first()
        )

    def _build_custom_fields(self, project):
        if project is None or project.project_type_id is None:
            return
        stored = self.instance.custom_fields or {}
        for definition in project.project_type.field_definitions.all():
            self._custom_definitions[definition.name] = definition
            field = self._form_field_for(definition)
            if definition.name in stored:
                field.initial = stored[definition.name]
            self.fields[f"{CUSTOM_PREFIX}{definition.name}"] = field

    def _form_field_for(self, definition):
        # Required is enforced centrally by validate_custom_fields, so the form
        # fields are optional; the label flags required ones for the user.
        label = definition.label + (" *" if definition.required else "")
        types = FieldDefinition.FieldType
        if definition.field_type == types.NUMBER:
            return forms.FloatField(label=label, required=False)
        if definition.field_type == types.DATE:
            return forms.DateField(label=label, required=False)
        if definition.field_type == types.CHOICE:
            choices = [("", "---------")] + [(c, c) for c in definition.choices]
            return forms.ChoiceField(label=label, required=False, choices=choices)
        if definition.field_type == types.BOOLEAN:
            return forms.BooleanField(label=label, required=False)
        return forms.CharField(label=label, required=False)

    # -- validation -----------------------------------------------------------

    def clean(self):
        cleaned = super().clean()
        raw = {}
        for name in self._custom_definitions:
            value = cleaned.get(f"{CUSTOM_PREFIX}{name}")
            if value is not None and value != "":
                raw[name] = value

        project = cleaned.get("project") or getattr(self.instance, "project", None)
        project_type = (
            project.project_type
            if project and project.project_type_id
            else None
        )
        try:
            self.instance.custom_fields = validate_custom_fields(project_type, raw)
        except ValidationError as exc:
            for field_name, messages in exc.message_dict.items():
                form_key = f"{CUSTOM_PREFIX}{field_name}"
                message = messages[0] if isinstance(messages, list) else messages
                if form_key in self.fields:
                    self.add_error(form_key, message)
                else:
                    self.add_error(None, f"{field_name}: {message}")
        return cleaned
