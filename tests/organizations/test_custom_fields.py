import datetime

import pytest
import test_helpers
from django.core.exceptions import ValidationError

from organizations.custom_fields import validate_custom_fields
from organizations.models import FieldDefinition

pytestmark = [pytest.mark.django_db]

FT = FieldDefinition.FieldType


def _typed():
    """A project type exercising every field kind (title_text is required)."""
    project_type = test_helpers.create_organizations_ProjectType(name="Sample")
    test_helpers.create_organizations_FieldDefinition(
        project_type=project_type, name="title_text", field_type=FT.TEXT, required=True
    )
    test_helpers.create_organizations_FieldDefinition(
        project_type=project_type, name="count", field_type=FT.NUMBER
    )
    test_helpers.create_organizations_FieldDefinition(
        project_type=project_type, name="due", field_type=FT.DATE
    )
    test_helpers.create_organizations_FieldDefinition(
        project_type=project_type, name="prio", field_type=FT.CHOICE,
        choices=["a", "b"],
    )
    test_helpers.create_organizations_FieldDefinition(
        project_type=project_type, name="flag", field_type=FT.BOOLEAN
    )
    return project_type


def tests_valid_input_normalizes():
    project_type = _typed()
    cleaned = validate_custom_fields(
        project_type,
        {
            "title_text": "hello",
            "count": 5,
            "due": datetime.date(2020, 1, 1),
            "prio": "a",
            "flag": True,
        },
    )
    assert cleaned == {
        "title_text": "hello",
        "count": 5,
        "due": "2020-01-01",  # date normalized to ISO string
        "prio": "a",
        "flag": True,
    }


def tests_date_iso_string_is_accepted():
    project_type = _typed()
    cleaned = validate_custom_fields(
        project_type, {"title_text": "x", "due": "2020-05-01"}
    )
    assert cleaned["due"] == "2020-05-01"


def tests_unknown_key_rejected():
    project_type = _typed()
    with pytest.raises(ValidationError) as exc:
        validate_custom_fields(project_type, {"title_text": "x", "bogus": 1})
    assert "bogus" in exc.value.message_dict


def tests_missing_required_rejected():
    project_type = _typed()
    with pytest.raises(ValidationError) as exc:
        validate_custom_fields(project_type, {})
    assert "title_text" in exc.value.message_dict


def tests_wrong_number_rejected():
    project_type = _typed()
    with pytest.raises(ValidationError) as exc:
        validate_custom_fields(project_type, {"title_text": "x", "count": "abc"})
    assert "count" in exc.value.message_dict


def tests_bad_date_rejected():
    project_type = _typed()
    with pytest.raises(ValidationError) as exc:
        validate_custom_fields(project_type, {"title_text": "x", "due": "nope"})
    assert "due" in exc.value.message_dict


def tests_choice_outside_list_rejected():
    project_type = _typed()
    with pytest.raises(ValidationError) as exc:
        validate_custom_fields(project_type, {"title_text": "x", "prio": "z"})
    assert "prio" in exc.value.message_dict


def tests_non_boolean_rejected():
    project_type = _typed()
    with pytest.raises(ValidationError) as exc:
        validate_custom_fields(project_type, {"title_text": "x", "flag": "yes"})
    assert "flag" in exc.value.message_dict


def tests_untyped_requires_empty():
    assert validate_custom_fields(None, {}) == {}
    with pytest.raises(ValidationError):
        validate_custom_fields(None, {"anything": 1})
