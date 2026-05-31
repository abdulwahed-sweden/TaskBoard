import pytest
import test_helpers
from django.core.exceptions import ValidationError

from organizations.workflow import (
    default_status,
    is_terminal_status,
    validate_status,
)

pytestmark = [pytest.mark.django_db]


def _workflow():
    """A project type with a 3-status workflow (open default, closed terminal)."""
    project_type = test_helpers.create_organizations_ProjectType(name="Flow")
    test_helpers.create_organizations_StatusDefinition(
        project_type=project_type, name="open", order=0, is_default=True
    )
    test_helpers.create_organizations_StatusDefinition(
        project_type=project_type, name="doing", order=1
    )
    test_helpers.create_organizations_StatusDefinition(
        project_type=project_type, name="closed", order=2, is_terminal=True
    )
    return project_type


def tests_untyped_requires_empty_status():
    assert validate_status(None, "") == ""
    with pytest.raises(ValidationError):
        validate_status(None, "anything")


def tests_type_without_workflow_requires_empty():
    project_type = test_helpers.create_organizations_ProjectType(name="NoFlow")
    assert validate_status(project_type, "") == ""
    with pytest.raises(ValidationError):
        validate_status(project_type, "open")


def tests_empty_resolves_to_default():
    project_type = _workflow()
    assert validate_status(project_type, "") == "open"
    assert default_status(project_type) == "open"


def tests_valid_status_passes():
    project_type = _workflow()
    assert validate_status(project_type, "doing") == "doing"


def tests_status_outside_set_rejected():
    project_type = _workflow()
    with pytest.raises(ValidationError):
        validate_status(project_type, "nonsense")


def tests_is_terminal_status():
    project_type = _workflow()
    assert is_terminal_status(project_type, "closed") is True
    assert is_terminal_status(project_type, "open") is False
    assert is_terminal_status(project_type, "") is False
    assert is_terminal_status(None, "closed") is False
