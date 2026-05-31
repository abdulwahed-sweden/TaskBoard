import pytest
import test_helpers
from django.urls import reverse
from rest_framework.test import APIClient

from organizations.models import Membership, ProjectType
from tasks.models import Task

pytestmark = [pytest.mark.django_db]

PASSWORD = "sup3r-secret-pw"


def _user_with_org(role=Membership.Role.MEMBER):
    user = test_helpers.create_User()
    user.set_password(PASSWORD)
    user.save()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(
        user=user, organization=org, role=role
    )
    project = test_helpers.create_organizations_Project(organization=org)
    return user, org, project


# --- token auth --------------------------------------------------------------

def tests_obtain_token_with_valid_credentials():
    user, _org, _project = _user_with_org()
    response = APIClient().post(
        reverse("api_token"),
        {"username": user.username, "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.data["token"]


def tests_obtain_token_with_bad_credentials():
    user, _org, _project = _user_with_org()
    response = APIClient().post(
        reverse("api_token"),
        {"username": user.username, "password": "wrong"},
    )
    assert response.status_code == 400


def tests_token_authenticates_requests():
    user, _org, project = _user_with_org()
    test_helpers.create_tasks_Task(owner=user, project=project)
    token = APIClient().post(
        reverse("api_token"),
        {"username": user.username, "password": PASSWORD},
    ).data["token"]

    api = APIClient()  # no session — token only
    api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    response = api.get(reverse("tasks:task-list"))
    assert response.status_code == 200
    assert response.data["count"] == 1


def tests_unauthenticated_still_forbidden():
    response = APIClient().get(reverse("tasks:task-list"))
    assert response.status_code == 403


# --- scoping survives token auth (key acceptance) ----------------------------

def tests_token_scoping_holds():
    user, _org, project = _user_with_org()
    mine = test_helpers.create_tasks_Task(owner=user, project=project)
    foreign = test_helpers.create_tasks_Task()  # another org
    token = APIClient().post(
        reverse("api_token"),
        {"username": user.username, "password": PASSWORD},
    ).data["token"]
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    listing = api.get(reverse("tasks:task-list"))
    ids = {row["id"] for row in listing.data["results"]}
    assert mine.pk in ids
    assert foreign.pk not in ids
    # And a foreign task 404s even with a valid token.
    assert api.get(
        reverse("tasks:task-detail", args=[foreign.pk])
    ).status_code == 404


# --- pagination / filtering / ordering ---------------------------------------

def _member_api():
    user, org, project = _user_with_org()
    api = APIClient()
    api.force_authenticate(user=user)
    return api, user, org, project


def tests_list_is_paginated():
    api, user, _org, project = _member_api()
    test_helpers.create_tasks_Task(owner=user, project=project)
    response = api.get(reverse("tasks:task-list"))
    assert set(response.data) >= {"count", "next", "previous", "results"}
    assert response.data["count"] == 1


def tests_filter_by_is_done():
    api, user, _org, project = _member_api()
    done = test_helpers.create_tasks_Task(owner=user, project=project, is_done=True)
    open_ = test_helpers.create_tasks_Task(owner=user, project=project, is_done=False)
    response = api.get(reverse("tasks:task-list"), {"is_done": "true"})
    ids = {row["id"] for row in response.data["results"]}
    assert done.pk in ids
    assert open_.pk not in ids


def tests_filter_by_project_within_scope():
    api, user, org, project = _member_api()
    other_project = test_helpers.create_organizations_Project(organization=org)
    here = test_helpers.create_tasks_Task(owner=user, project=project)
    there = test_helpers.create_tasks_Task(owner=user, project=other_project)
    response = api.get(reverse("tasks:task-list"), {"project": project.pk})
    ids = {row["id"] for row in response.data["results"]}
    assert here.pk in ids
    assert there.pk not in ids


def tests_ordering_by_title():
    api, user, _org, project = _member_api()
    test_helpers.create_tasks_Task(owner=user, project=project, title="bravo")
    test_helpers.create_tasks_Task(owner=user, project=project, title="alpha")
    response = api.get(reverse("tasks:task-list"), {"ordering": "title"})
    titles = [row["title"] for row in response.data["results"]]
    assert titles == sorted(titles)


def tests_search_by_title():
    api, user, _org, project = _member_api()
    match = test_helpers.create_tasks_Task(
        owner=user, project=project, title="deploy pipeline"
    )
    test_helpers.create_tasks_Task(owner=user, project=project, title="write docs")
    response = api.get(reverse("tasks:task-list"), {"search": "deploy"})
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {match.pk}


# --- schema & docs -----------------------------------------------------------

def tests_schema_endpoint(client):
    assert client.get(reverse("schema")).status_code == 200


def tests_docs_endpoint(client):
    assert client.get(reverse("swagger-ui")).status_code == 200
