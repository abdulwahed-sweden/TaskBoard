import pytest
import test_helpers
from django.urls import reverse
from rest_framework.test import APIClient

from organizations.models import Membership, ProjectType
from organizations.sessions import SESSION_KEY
from tasks import notifications
from tasks.models import NotificationPreference, Task

pytestmark = [pytest.mark.django_db]


def _project_with_members(*users, project_type=None):
    org = test_helpers.create_organizations_Organization()
    for user in users:
        test_helpers.create_organizations_Membership(user=user, organization=org)
    project = test_helpers.create_organizations_Project(
        organization=org, project_type=project_type
    )
    return org, project


# --- service: events ---------------------------------------------------------

def tests_assignment_emails_the_assignee(mailoutbox):
    actor = test_helpers.create_User()
    assignee = test_helpers.create_User(email="assignee@example.com")
    _org, project = _project_with_members(actor, assignee)
    task = test_helpers.create_tasks_Task(owner=assignee, project=project)

    notifications.on_task_created(task, actor)
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["assignee@example.com"]
    assert task.title in mailoutbox[0].subject


def tests_no_email_when_actor_is_the_assignee(mailoutbox):
    user = test_helpers.create_User()
    _org, project = _project_with_members(user)
    task = test_helpers.create_tasks_Task(owner=user, project=project)

    notifications.on_task_created(task, user)
    assert mailoutbox == []


def tests_comment_emails_the_assignee(mailoutbox):
    assignee = test_helpers.create_User(email="b@example.com")
    commenter = test_helpers.create_User()
    _org, project = _project_with_members(assignee, commenter)
    task = test_helpers.create_tasks_Task(owner=assignee, project=project)

    notifications.notify_comment(task, commenter)
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["b@example.com"]


def tests_status_change_emails_the_assignee(mailoutbox):
    actor = test_helpers.create_User()
    assignee = test_helpers.create_User(email="b@example.com")
    _org, project = _project_with_members(
        actor, assignee, project_type=ProjectType.objects.get(name="Software Tasks")
    )
    task = test_helpers.create_tasks_Task(
        owner=assignee, project=project, status="backlog"
    )
    task.status = "in_progress"

    notifications.on_task_updated(
        task, actor, {"status": "backlog", "owner_id": task.owner_id}
    )
    assert len(mailoutbox) == 1
    assert "Status changed" in mailoutbox[0].subject


# --- service: preferences & guards ------------------------------------------

def tests_preference_off_suppresses_email(mailoutbox):
    actor = test_helpers.create_User()
    assignee = test_helpers.create_User(email="b@example.com")
    NotificationPreference.objects.create(
        user=assignee, notify_on_assignment=False
    )
    _org, project = _project_with_members(actor, assignee)
    task = test_helpers.create_tasks_Task(owner=assignee, project=project)

    notifications.on_task_created(task, actor)
    assert mailoutbox == []


def tests_no_email_without_address(mailoutbox):
    actor = test_helpers.create_User()
    assignee = test_helpers.create_User(email="")
    _org, project = _project_with_members(actor, assignee)
    task = test_helpers.create_tasks_Task(owner=assignee, project=project)

    notifications.on_task_created(task, actor)
    assert mailoutbox == []


def tests_no_email_without_assignee(mailoutbox):
    actor = test_helpers.create_User()
    project = test_helpers.create_organizations_Project()
    task = test_helpers.create_tasks_Task(owner=None, project=project)

    notifications.on_task_created(task, actor)
    assert mailoutbox == []


# --- integration: web + API --------------------------------------------------

def _logged_in_member(client):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(user=user, organization=org)
    project = test_helpers.create_organizations_Project(organization=org)
    client.force_login(user)
    session = client.session
    session[SESSION_KEY] = org.pk
    session.save()
    return user, org, project


def tests_web_assignment_sends_email(client, mailoutbox):
    user, org, project = _logged_in_member(client)
    other = test_helpers.create_User(email="other@example.com")
    test_helpers.create_organizations_Membership(user=other, organization=org)

    response = client.post(
        reverse("tasks:Task_create"),
        {"project": project.pk, "owner": other.pk, "title": "assigned-task"},
    )
    assert response.status_code == 302
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["other@example.com"]


def tests_api_assignment_sends_email(mailoutbox):
    user = test_helpers.create_User()
    other = test_helpers.create_User(email="other@example.com")
    _org, project = _project_with_members(user, other)
    api = APIClient()
    api.force_authenticate(user=user)

    response = api.post(
        reverse("tasks:task-list"),
        {"title": "via-api", "project": project.pk, "owner": other.pk},
        format="json",
    )
    assert response.status_code == 201
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["other@example.com"]


def tests_preferences_page_updates(client):
    user, _org, _project = _logged_in_member(client)
    response = client.post(
        reverse("notification_preferences"),
        {"notify_on_comment": "on"},  # assignment & status unchecked -> off
    )
    assert response.status_code == 302
    preference = NotificationPreference.objects.get(user=user)
    assert preference.notify_on_comment is True
    assert preference.notify_on_assignment is False
    assert preference.notify_on_status_change is False
