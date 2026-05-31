import pytest
import test_helpers
from django.urls import reverse
from rest_framework.test import APIClient

from organizations.models import Membership, ProjectType
from organizations.sessions import SESSION_KEY
from tasks.models import Activity, Task

pytestmark = [pytest.mark.django_db]


def _api_member(role=Membership.Role.MEMBER):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    api = APIClient()
    api.force_authenticate(user=user)
    return api, user, org


def _software_project(org):
    return test_helpers.create_organizations_Project(
        organization=org, project_type=ProjectType.objects.get(name="Software Tasks")
    )


# --- created -----------------------------------------------------------------

def tests_web_create_logs_created(client):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(user=user, organization=org)
    project = test_helpers.create_organizations_Project(organization=org)
    client.force_login(user)
    session = client.session
    session[SESSION_KEY] = org.pk
    session.save()

    client.post(
        reverse("tasks:Task_create"), {"project": project.pk, "title": "web-task"}
    )
    task = Task.objects.get(title="web-task")
    activities = list(task.activities.all())
    assert len(activities) == 1
    assert activities[0].action == Activity.Action.CREATED


def tests_api_create_logs_created():
    api, user, org = _api_member()
    project = test_helpers.create_organizations_Project(organization=org)
    response = api.post(
        reverse("tasks:task-list"),
        {"title": "api-task", "project": project.pk},
        format="json",
    )
    assert response.status_code == 201
    task = Task.objects.get(title="api-task")
    assert task.activities.filter(action=Activity.Action.CREATED).count() == 1


# --- status change / assignment / generic update -----------------------------

def tests_status_change_logs_activity():
    api, user, org = _api_member()
    project = _software_project(org)
    response = api.post(
        reverse("tasks:task-list"),
        {
            "title": "t",
            "project": project.pk,
            "custom_fields": {"priority": "Low"},
            "status": "backlog",
        },
        format="json",
    )
    assert response.status_code == 201
    task = Task.objects.get(title="t")

    response = api.patch(
        reverse("tasks:task-detail", args=[task.pk]),
        {"status": "in_progress"},
        format="json",
    )
    assert response.status_code == 200
    activity = task.activities.filter(
        action=Activity.Action.STATUS_CHANGED
    ).first()
    assert activity is not None
    assert activity.detail == {"from": "backlog", "to": "in_progress"}


def tests_reassign_logs_assigned():
    api, user, org = _api_member()
    other = test_helpers.create_User()
    test_helpers.create_organizations_Membership(user=other, organization=org)
    project = test_helpers.create_organizations_Project(organization=org)
    response = api.post(
        reverse("tasks:task-list"),
        {"title": "t", "project": project.pk},
        format="json",
    )
    task = Task.objects.get(title="t")  # owner defaults to the creator

    response = api.patch(
        reverse("tasks:task-detail", args=[task.pk]),
        {"owner": other.pk},
        format="json",
    )
    assert response.status_code == 200
    activity = task.activities.filter(action=Activity.Action.ASSIGNED).first()
    assert activity is not None
    assert activity.detail == {"to": other.username}


def tests_plain_edit_logs_updated():
    api, user, org = _api_member()
    project = test_helpers.create_organizations_Project(organization=org)
    response = api.post(
        reverse("tasks:task-list"),
        {"title": "t", "project": project.pk},
        format="json",
    )
    task = Task.objects.get(title="t")

    response = api.patch(
        reverse("tasks:task-detail", args=[task.pk]),
        {"title": "renamed"},
        format="json",
    )
    assert response.status_code == 200
    assert task.activities.filter(action=Activity.Action.UPDATED).count() == 1
    assert not task.activities.filter(
        action=Activity.Action.STATUS_CHANGED
    ).exists()


# --- log properties ----------------------------------------------------------

def tests_activity_is_newest_first():
    api, user, org = _api_member()
    project = test_helpers.create_organizations_Project(organization=org)
    api.post(
        reverse("tasks:task-list"),
        {"title": "t", "project": project.pk},
        format="json",
    )
    task = Task.objects.get(title="t")
    api.patch(
        reverse("tasks:task-detail", args=[task.pk]),
        {"title": "renamed"},
        format="json",
    )
    actions = [a.action for a in task.activities.all()]
    assert actions[0] == Activity.Action.UPDATED
    assert actions[-1] == Activity.Action.CREATED


def tests_raw_save_logs_nothing():
    # The factory uses Model.objects.create (not an app write path), so no
    # activity is recorded — the log is driven by user actions only.
    task = test_helpers.create_tasks_Task()
    assert task.activities.count() == 0
