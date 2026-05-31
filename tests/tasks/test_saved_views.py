import pytest
import test_helpers
from django.urls import reverse

from organizations.models import Membership
from organizations.sessions import SESSION_KEY
from tasks.models import SavedView

pytestmark = [pytest.mark.django_db]


def _member(client, role=Membership.Role.MEMBER):
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


def tests_save_view_persists_and_reloads(client):
    user, org, project = _member(client)
    done = test_helpers.create_tasks_Task(
        project=project, owner=user, title="finished-job", status="done", is_done=True
    )
    open_ = test_helpers.create_tasks_Task(
        project=project, owner=user, title="pending-job", status="todo", is_done=False
    )

    response = client.post(
        reverse("tasks:savedview_create"),
        {"project": project.pk, "name": "Completed", "is_done": "true"},
    )
    assert response.status_code == 302
    view = SavedView.objects.get(project=project, name="Completed")
    assert view.filters == {"is_done": "true"}

    # Reloading the saved view's querystring reproduces the filtered set.
    reload = client.get(reverse("tasks:Task_list") + "?" + view.querystring())
    body = reload.content.decode("utf-8")
    assert str(done) in body
    assert str(open_) not in body


def tests_saved_view_is_shared_within_org(client):
    creator, org, project = _member(client)
    SavedView.objects.create(project=project, name="Shared", created_by=creator)

    other = test_helpers.create_User()
    test_helpers.create_organizations_Membership(user=other, organization=org)
    other_client = client.__class__()
    other_client.force_login(other)
    session = other_client.session
    session[SESSION_KEY] = org.pk
    session.save()

    response = other_client.get(
        reverse("tasks:Task_list") + f"?project={project.pk}"
    )
    assert "Shared" in response.content.decode("utf-8")


def tests_save_view_forbidden_for_viewer(client):
    user, org, project = _member(client, role=Membership.Role.VIEWER)
    response = client.post(
        reverse("tasks:savedview_create"),
        {"project": project.pk, "name": "Nope"},
    )
    assert response.status_code == 403
    assert not SavedView.objects.filter(name="Nope").exists()


def tests_save_view_foreign_project_404(client):
    _member(client)
    foreign = test_helpers.create_organizations_Project()  # different org
    response = client.post(
        reverse("tasks:savedview_create"),
        {"project": foreign.pk, "name": "X"},
    )
    assert response.status_code == 404


def tests_delete_saved_view(client):
    user, org, project = _member(client)
    view = SavedView.objects.create(
        project=project, name="Temp", created_by=user
    )
    response = client.post(reverse("tasks:savedview_delete", args=[view.pk]))
    assert response.status_code == 302
    assert not SavedView.objects.filter(pk=view.pk).exists()


def tests_saved_view_name_unique_per_project(client):
    user, org, project = _member(client)
    SavedView.objects.create(project=project, name="Dup", created_by=user)
    # Saving again with the same name updates rather than duplicating.
    client.post(
        reverse("tasks:savedview_create"),
        {"project": project.pk, "name": "Dup", "is_done": "false"},
    )
    views = SavedView.objects.filter(project=project, name="Dup")
    assert views.count() == 1
    assert views.first().filters == {"is_done": "false"}
