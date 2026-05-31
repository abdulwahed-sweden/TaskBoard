"""Validation for ``Task.status`` against a project type's workflow.

Single source of truth (like ``custom_fields``), reused by the task form, the
DRF serializer, and the model. A project type with no status definitions means
"no workflow": the task's status must stay empty and ``is_done`` is edited
directly (Phase 1–3 behavior).
"""

from django.core.exceptions import ValidationError


def status_definitions_for(project):
    """Ordered status definitions for a project's type ( [] if untyped )."""
    if project is None or project.project_type_id is None:
        return []
    return list(project.project_type.status_definitions.all())


def default_status(project_type):
    """The status new typed tasks start in: the ``is_default`` one, else the
    first by order, else ``""`` (no workflow)."""
    if project_type is None:
        return ""
    definitions = list(project_type.status_definitions.all())
    if not definitions:
        return ""
    for definition in definitions:
        if definition.is_default:
            return definition.name
    return definitions[0].name


def validate_status(project_type, status):
    """Resolve and validate ``status`` for ``project_type``; returns the
    resolved status name. Raises ``ValidationError`` for a value outside the
    workflow (or any value when the type has no workflow)."""
    status = status or ""
    definitions = (
        list(project_type.status_definitions.all()) if project_type else []
    )

    if not definitions:
        if status:
            raise ValidationError(
                "This project has no workflow, so status must be empty."
            )
        return ""

    if not status:
        return default_status(project_type)

    if status not in {definition.name for definition in definitions}:
        raise ValidationError(f"'{status}' is not a valid status for this project.")
    return status


def is_terminal_status(project_type, status):
    """Whether ``status`` is a terminal status of ``project_type`` (used to keep
    ``Task.is_done`` in sync). False when untyped or status unknown."""
    if project_type is None or not status:
        return False
    return project_type.status_definitions.filter(
        name=status, is_terminal=True
    ).exists()
