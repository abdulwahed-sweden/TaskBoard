"""Validation for ``Task.custom_fields`` against a project type's schema.

This is the single source of truth, reused by the task form, the DRF serializer,
and (later) the data importer. It works on plain dicts so it is independent of
any form/serializer machinery.
"""

import datetime

from django.core.exceptions import ValidationError

from .models import FieldDefinition


def field_definitions_for(project):
    """Ordered field definitions for a project's type ( [] if untyped )."""
    if project is None or project.project_type_id is None:
        return []
    return list(project.project_type.field_definitions.all())


def _normalize_value(definition, value):
    """Validate and normalize one value to a JSON-serializable form.

    Raises ``ValueError`` with a human message on a bad value.
    """
    field_type = definition.field_type
    types = FieldDefinition.FieldType

    if field_type == types.TEXT:
        if not isinstance(value, str):
            raise ValueError("Enter text.")
        return value

    if field_type == types.NUMBER:
        # bool is a subclass of int — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Enter a number.")
        return value

    if field_type == types.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError("Enter true or false.")
        return value

    if field_type == types.CHOICE:
        if value not in definition.choices:
            raise ValueError("Select a valid choice.")
        return value

    if field_type == types.DATE:
        if isinstance(value, datetime.datetime):
            value = value.date()
        if isinstance(value, datetime.date):
            return value.isoformat()
        if isinstance(value, str):
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                raise ValueError("Enter a date (YYYY-MM-DD).")
            return value
        raise ValueError("Enter a date (YYYY-MM-DD).")

    raise ValueError("Unknown field type.")


def validate_custom_fields(project_type, raw):
    """Validate ``raw`` against ``project_type`` and return a normalized dict.

    Rejects unknown keys, enforces required fields, and checks/normalizes each
    value's type. Raises ``django.core.exceptions.ValidationError`` whose
    ``message_dict`` maps field name → message. A ``None`` project type permits
    only an empty mapping.
    """
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ValidationError("Custom fields must be a mapping of field to value.")

    if project_type is None:
        if raw:
            raise ValidationError(
                "This project has no type, so it accepts no custom fields."
            )
        return {}

    definitions = {d.name: d for d in project_type.field_definitions.all()}
    errors = {}

    for key in raw:
        if key not in definitions:
            errors[key] = "Unknown field."

    cleaned = {}
    for name, definition in definitions.items():
        value = raw.get(name)
        if value is None or value == "":
            if definition.required:
                errors[name] = "This field is required."
            continue
        try:
            cleaned[name] = _normalize_value(definition, value)
        except ValueError as exc:
            errors[name] = str(exc)

    if errors:
        raise ValidationError(errors)
    return cleaned
