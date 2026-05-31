
import pytest
import test_helpers
from django.urls import reverse
from rest_framework.test import APIClient

from organizations.models import Membership
from organizations.sessions import SESSION_KEY
from tasks.models import Task

pytestmark = [pytest.mark.django_db]


def _member(client, role=Membership.Role.MEMBER):
    """Log in a user who belongs to a fresh org (with ``role``) and make that
    org active. Returns (user, organization, project)."""
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    project = test_helpers.create_organizations_Project(organization=org)
    client.force_login(user)
    session = client.session
    session[SESSION_KEY] = org.pk
    session.save()
    return user, org, project


# --- task list (active-org scoped) ------------------------------------------

def tests_Task_list_view(client):
    user, org, project = _member(client)
    a = test_helpers.create_tasks_Task(owner=user, project=project, title="alpha")
    b = test_helpers.create_tasks_Task(owner=user, project=project, title="bravo")
    response = client.get(reverse("tasks:Task_list"))
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert str(a) in body
    assert str(b) in body


def tests_Task_list_view_requires_login(client):
    response = client.get(reverse("tasks:Task_list"))
    assert response.status_code == 302
    assert reverse("login") in response.url


def tests_Task_list_view_only_shows_active_org_tasks(client):
    user, org, project = _member(client)
    mine = test_helpers.create_tasks_Task(owner=user, project=project, title="mine")
    # A task in a different org the user does not belong to.
    theirs = test_helpers.create_tasks_Task(title="theirs")
    response = client.get(reverse("tasks:Task_list"))
    body = response.content.decode("utf-8")
    assert str(mine) in body
    assert str(theirs) not in body


def tests_Task_list_view_filters_by_project(client):
    user, org, first = _member(client)
    second = test_helpers.create_organizations_Project(organization=org)
    in_first = test_helpers.create_tasks_Task(
        owner=user, project=first, title="in-first"
    )
    in_second = test_helpers.create_tasks_Task(
        owner=user, project=second, title="in-second"
    )
    response = client.get(reverse("tasks:Task_list"), {"project": first.pk})
    body = response.content.decode("utf-8")
    assert str(in_first) in body
    assert str(in_second) not in body


# --- create (members+) ------------------------------------------------------

def tests_Task_create_view_files_into_project_and_sets_owner(client):
    user, org, project = _member(client)
    response = client.post(
        reverse("tasks:Task_create"),
        {
            "project": project.pk,
            "title": "fresh-task",
            "notes": "some\ntext",
            "is_done": True,
            "due_date": "2022-01-01",
        },
    )
    assert response.status_code == 302
    task = Task.objects.get(title="fresh-task")
    assert task.owner == user
    assert task.project == project


def tests_Task_create_view_forbidden_for_viewer(client):
    _member(client, role=Membership.Role.VIEWER)
    response = client.get(reverse("tasks:Task_create"))
    assert response.status_code == 403


# --- detail / update / delete scoping ---------------------------------------

def tests_Task_detail_view(client):
    user, org, project = _member(client)
    task = test_helpers.create_tasks_Task(owner=user, project=project)
    response = client.get(reverse("tasks:Task_detail", args=[task.pk]))
    assert response.status_code == 200
    assert str(task) in response.content.decode("utf-8")


def tests_Task_detail_view_other_org_404(client):
    _member(client)
    # Task in a different org the logged-in user is not a member of.
    foreign = test_helpers.create_tasks_Task()
    response = client.get(reverse("tasks:Task_detail", args=[foreign.pk]))
    assert response.status_code == 404


def tests_Task_update_view(client):
    user, org, project = _member(client)
    task = test_helpers.create_tasks_Task(owner=user, project=project)
    response = client.post(
        reverse("tasks:Task_update", args=[task.pk]),
        {
            "project": project.pk,
            "title": "renamed",
            "notes": "some\ntext",
            "is_done": True,
            "due_date": "2022-01-01",
        },
    )
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.title == "renamed"


def tests_Task_update_view_forbidden_for_viewer(client):
    user, org, project = _member(client, role=Membership.Role.VIEWER)
    task = test_helpers.create_tasks_Task(owner=user, project=project)
    response = client.get(reverse("tasks:Task_update", args=[task.pk]))
    assert response.status_code == 403


def tests_Task_update_view_other_org_404(client):
    _member(client)
    foreign = test_helpers.create_tasks_Task()
    response = client.get(reverse("tasks:Task_update", args=[foreign.pk]))
    assert response.status_code == 404


def tests_Task_delete_view_forbidden_for_viewer(client):
    user, org, project = _member(client, role=Membership.Role.VIEWER)
    task = test_helpers.create_tasks_Task(owner=user, project=project)
    response = client.post(reverse("tasks:Task_delete", args=[task.pk]))
    assert response.status_code == 403
    assert Task.objects.filter(pk=task.pk).exists()


# --- REST API scoping -------------------------------------------------------

def _api_for(role=Membership.Role.MEMBER):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    project = test_helpers.create_organizations_Project(organization=org)
    api = APIClient()
    api.force_authenticate(user=user)
    return api, user, org, project


def tests_api_requires_authentication():
    response = APIClient().get(reverse("tasks:task-list"))
    assert response.status_code == 403


def tests_api_lists_only_own_org_tasks():
    api, user, org, project = _api_for()
    mine = test_helpers.create_tasks_Task(owner=user, project=project)
    theirs = test_helpers.create_tasks_Task()  # foreign org
    response = api.get(reverse("tasks:task-list"))
    assert response.status_code == 200
    ids = {row["id"] for row in response.data}
    assert mine.pk in ids
    assert theirs.pk not in ids


def tests_api_cannot_read_foreign_org_task():
    api, user, org, project = _api_for()
    foreign = test_helpers.create_tasks_Task()
    response = api.get(reverse("tasks:task-detail", args=[foreign.pk]))
    assert response.status_code == 404


def tests_api_create_into_own_project_sets_owner():
    api, user, org, project = _api_for()
    response = api.post(
        reverse("tasks:task-list"),
        {"title": "via-api", "project": project.pk},
        format="json",
    )
    assert response.status_code == 201
    task = Task.objects.get(title="via-api")
    assert task.owner == user
    assert task.project == project


def tests_api_create_into_foreign_project_rejected():
    api, user, org, project = _api_for()
    foreign_project = test_helpers.create_organizations_Project()
    response = api.post(
        reverse("tasks:task-list"),
        {"title": "sneaky", "project": foreign_project.pk},
        format="json",
    )
    assert response.status_code == 400
    assert not Task.objects.filter(title="sneaky").exists()


def tests_api_viewer_cannot_update_task():
    api, user, org, project = _api_for(role=Membership.Role.VIEWER)
    task = test_helpers.create_tasks_Task(owner=user, project=project)
    response = api.patch(
        reverse("tasks:task-detail", args=[task.pk]),
        {"title": "nope"},
        format="json",
    )
    assert response.status_code == 403


# --- accounts (unchanged behaviour) -----------------------------------------

def tests_signup_view_creates_user(client):
    from django.contrib.auth.models import User

    url = reverse("signup")
    assert client.get(url).status_code == 200
    response = client.post(url, {
        "username": "newcomer",
        "password1": "sup3r-secret-pw",
        "password2": "sup3r-secret-pw",
    })
    assert response.status_code == 302
    assert User.objects.filter(username="newcomer").exists()


def tests_profile_view_requires_login(client):
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert reverse("login") in response.url


def tests_profile_view_shows_own_tasks(client):
    user = test_helpers.create_User()
    client.force_login(user)
    test_helpers.create_tasks_Task(owner=user, title="profile-task")
    response = client.get(reverse("profile"))
    assert response.status_code == 200
    assert "profile-task" in response.content.decode("utf-8")


def tests_password_reset_sends_email(client, mailoutbox):
    user = test_helpers.create_User(email="resetme@example.com")
    assert client.get(reverse("password_reset")).status_code == 200
    response = client.post(reverse("password_reset"), {"email": user.email})
    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")
    assert len(mailoutbox) == 1
    email = mailoutbox[0]
    assert email.subject == "Reset your TaskBoard password"
    assert user.email in email.to
    assert "choose a new password" in email.body


def tests_password_reset_unknown_email_sends_nothing(client, mailoutbox):
    response = client.post(reverse("password_reset"), {"email": "nobody@example.com"})
    assert response.status_code == 302
    assert len(mailoutbox) == 0


def tests_change_password_updates_credentials(client):
    user = test_helpers.create_User()
    user.set_password("original-pw-123")
    user.save()
    client.force_login(user)
    assert client.get(reverse("password_change")).status_code == 200
    response = client.post(reverse("password_change"), {
        "old_password": "original-pw-123",
        "new_password1": "brand-new-pw-456",
        "new_password2": "brand-new-pw-456",
    })
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("brand-new-pw-456")
