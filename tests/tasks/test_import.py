import io

import pytest
import test_helpers
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from organizations.models import Membership, ProjectType
from organizations.sessions import SESSION_KEY
from tasks import importer
from tasks.models import Activity, Task

pytestmark = [pytest.mark.django_db]


def _software_project():
    return test_helpers.create_organizations_Project(
        project_type=ProjectType.objects.get(name="Software Tasks")
    )


def _translation_project():
    return test_helpers.create_organizations_Project(
        project_type=ProjectType.objects.get(name="Translation Jobs")
    )


# --- parsing -----------------------------------------------------------------

def tests_parse_csv():
    data = io.BytesIO(b"Title,Notes\nBuild,hello\nShip,world\n")
    headers, rows = importer.parse_upload(data, "tasks.csv")
    assert headers == ["Title", "Notes"]
    assert rows == [
        {"Title": "Build", "Notes": "hello"},
        {"Title": "Ship", "Notes": "world"},
    ]


def tests_parse_xlsx():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Title", "Priority"])
    sheet.append(["Build", "High"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    headers, rows = importer.parse_upload(buffer, "tasks.xlsx")
    assert headers == ["Title", "Priority"]
    assert rows == [{"Title": "Build", "Priority": "High"}]


def tests_parse_unsupported_type():
    with pytest.raises(importer.ImportError):
        importer.parse_upload(io.BytesIO(b"x"), "tasks.txt")


def tests_parse_empty_file():
    with pytest.raises(importer.ImportError):
        importer.parse_upload(io.BytesIO(b"Title,Notes\n"), "tasks.csv")


def tests_parse_too_many_rows(monkeypatch):
    monkeypatch.setattr(importer, "MAX_ROWS", 2)
    data = io.BytesIO(b"Title\na\nb\nc\n")
    with pytest.raises(importer.ImportError):
        importer.parse_upload(data, "tasks.csv")


# --- mapping -----------------------------------------------------------------

def tests_map_row_drops_unmapped_and_blank():
    row = {"A": "1", "B": "2", "C": ""}
    mapping = {"title": "A", "notes": "C", "status": ""}
    # B is unmapped, C is blank, status maps to an empty column -> all dropped.
    assert importer.map_row(row, mapping) == {"title": "1"}


def tests_auto_mapping_matches_by_name_and_label():
    project = _software_project()
    mapping = importer.auto_mapping(project, ["Title", "Priority", "Nope"])
    assert mapping["title"] == "Title"
    assert mapping["custom_priority"] == "Priority"
    assert "status" not in mapping or mapping.get("status") != "Nope"


# --- per-row validation ------------------------------------------------------

def tests_clean_row_requires_title():
    project = _software_project()
    _data, errors = importer.clean_row(project, {"custom_priority": "Low"})
    assert "title" in errors


def tests_clean_row_bad_due_date():
    project = _software_project()
    _data, errors = importer.clean_row(
        project, {"title": "x", "due_date": "nope", "custom_priority": "Low"}
    )
    assert "due_date" in errors


def tests_clean_row_status_out_of_set():
    project = _software_project()
    _data, errors = importer.clean_row(
        project, {"title": "x", "status": "bogus", "custom_priority": "Low"}
    )
    assert "status" in errors


def tests_clean_row_choice_outside_list():
    project = _software_project()
    _data, errors = importer.clean_row(
        project, {"title": "x", "custom_priority": "Urgent"}
    )
    assert "custom_priority" in errors


def tests_clean_row_unknown_custom_field():
    project = _software_project()
    _data, errors = importer.clean_row(
        project, {"title": "x", "custom_priority": "Low", "custom_bogus": "y"}
    )
    assert "custom_bogus" in errors


def tests_clean_row_valid_software():
    project = _software_project()
    data, errors = importer.clean_row(
        project, {"title": "Build", "custom_priority": "Low"}
    )
    assert errors == {}
    assert data["custom_fields"] == {"priority": "Low"}
    assert data["status"] == "backlog"  # resolved to the default


def tests_clean_row_coerces_number():
    project = _translation_project()
    data, errors = importer.clean_row(
        project,
        {
            "title": "Job",
            "custom_source_lang": "en",
            "custom_target_lang": "sv",
            "custom_word_count": "1200",
        },
    )
    assert errors == {}
    assert data["custom_fields"]["word_count"] == 1200


def tests_clean_row_bad_number():
    project = _translation_project()
    _data, errors = importer.clean_row(
        project,
        {
            "title": "Job",
            "custom_source_lang": "en",
            "custom_target_lang": "sv",
            "custom_word_count": "lots",
        },
    )
    assert "custom_word_count" in errors


# --- commit (partial) --------------------------------------------------------

def tests_commit_imports_valid_and_reports_skipped():
    project = _software_project()
    user = test_helpers.create_User()
    rows = [
        {"Title": "Build", "Priority": "High"},
        {"Title": "", "Priority": "Low"},  # missing title -> skipped
    ]
    mapping = {"title": "Title", "custom_priority": "Priority"}
    result = importer.commit(project, rows, mapping, owner=user)

    assert result["created"] == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["row_number"] == 2
    assert "title" in result["skipped"][0]["errors"]

    task = Task.objects.get(project=project)
    assert task.title == "Build"
    assert task.custom_fields == {"priority": "High"}
    assert task.status == "backlog"
    assert task.activities.filter(action=Activity.Action.CREATED).count() == 1


# --- web flow ----------------------------------------------------------------

def _member(client, role=Membership.Role.MEMBER):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    client.force_login(user)
    session = client.session
    session[SESSION_KEY] = org.pk
    session.save()
    return user, org


def tests_import_web_flow_commits_valid_rows(client):
    user, org = _member(client)
    project = test_helpers.create_organizations_Project(
        organization=org, project_type=ProjectType.objects.get(name="Software Tasks")
    )
    csv = b"Title,Priority,Status\nBuild login,High,backlog\n,Low,backlog\n"
    upload = SimpleUploadedFile("tasks.csv", csv, content_type="text/csv")
    response = client.post(
        reverse("tasks:import"), {"project": project.pk, "file": upload}
    )
    assert response.status_code == 302

    response = client.post(
        reverse("tasks:import_map"),
        {
            "action": "commit",
            "map_title": "Title",
            "map_custom_priority": "Priority",
            "map_status": "Status",
        },
    )
    assert response.status_code == 200
    tasks = Task.objects.filter(project=project)
    assert tasks.count() == 1
    task = tasks.first()
    assert task.title == "Build login"
    assert task.custom_fields == {"priority": "High"}
    assert task.status == "backlog"


def tests_import_forbidden_for_viewer(client):
    _member(client, role=Membership.Role.VIEWER)
    assert client.get(reverse("tasks:import")).status_code == 403


def tests_import_rejects_project_outside_active_org(client):
    _member(client)
    outside = test_helpers.create_organizations_Project()  # different org
    upload = SimpleUploadedFile("t.csv", b"Title\nA\n", content_type="text/csv")
    response = client.post(
        reverse("tasks:import"), {"project": outside.pk, "file": upload}
    )
    assert response.status_code == 404
