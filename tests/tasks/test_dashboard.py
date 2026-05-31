import pytest
import test_helpers
from django.urls import reverse

from organizations.models import Membership
from organizations.sessions import SESSION_KEY
from tasks.models import Activity

pytestmark = [pytest.mark.django_db]


def _member_with_org(client):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(user=user, organization=org)
    project = test_helpers.create_organizations_Project(organization=org)
    client.force_login(user)
    session = client.session
    session[SESSION_KEY] = org.pk
    session.save()
    return user, org, project


def tests_dashboard_counts_match_active_org(client):
    user, org, project = _member_with_org(client)
    test_helpers.create_tasks_Task(
        project=project, owner=user, status="todo", is_done=False, due_date="2999-01-01"
    )
    test_helpers.create_tasks_Task(
        project=project, owner=user, status="todo", is_done=False, due_date="2000-01-01"
    )  # overdue
    test_helpers.create_tasks_Task(
        project=project, owner=user, status="done", is_done=True, due_date="2000-01-01"
    )
    test_helpers.create_tasks_Task()  # different org — must be excluded

    response = client.get(reverse("tasks:dashboard"))
    assert response.status_code == 200
    context = response.context
    assert context["total"] == 3
    assert context["open_count"] == 2
    assert context["done_count"] == 1
    assert context["overdue_count"] == 1
    counts = {row["status"]: row["count"] for row in context["status_counts"]}
    assert counts == {"todo": 2, "done": 1}


def tests_dashboard_recent_activity_scoped(client):
    user, org, project = _member_with_org(client)
    mine = test_helpers.create_tasks_Task(project=project, owner=user)
    foreign = test_helpers.create_tasks_Task()
    Activity.objects.create(
        task=mine, actor=user, action=Activity.Action.CREATED, description="mine-act"
    )
    Activity.objects.create(
        task=foreign, actor=None, action=Activity.Action.CREATED,
        description="foreign-act",
    )

    response = client.get(reverse("tasks:dashboard"))
    descriptions = [a.description for a in response.context["recent_activity"]]
    assert "mine-act" in descriptions
    assert "foreign-act" not in descriptions


def tests_dashboard_requires_login(client):
    response = client.get(reverse("tasks:dashboard"))
    assert response.status_code == 302
    assert reverse("login") in response.url
