import pytest
import test_helpers
from django.urls import reverse

from organizations.custom_fields import validate_custom_fields
from organizations.models import (
    FieldDefinition,
    Membership,
    Organization,
    Project,
    ProjectType,
    role_rank,
)
from organizations.permissions import RequireRoleMixin, has_role
from organizations.services import create_personal_organization
from organizations.sessions import (
    SESSION_KEY,
    get_active_organization,
    set_active_organization,
)

pytestmark = [pytest.mark.django_db]


# --- signup creates a personal org ------------------------------------------

def tests_signup_creates_personal_organization(client):
    from django.contrib.auth.models import User

    response = client.post(
        reverse("signup"),
        {
            "username": "founder",
            "password1": "sup3r-secret-pw",
            "password2": "sup3r-secret-pw",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(username="founder")
    membership = Membership.objects.get(user=user)
    assert membership.role == Membership.Role.OWNER
    assert membership.organization.name == "founder's Organization"
    assert user.organizations.count() == 1


# --- create_personal_organization helper ------------------------------------

def tests_create_personal_organization_makes_owner(client):
    user = test_helpers.create_User(username="solo")
    org = create_personal_organization(user)
    assert isinstance(org, Organization)
    assert has_role(user, org, Membership.Role.OWNER)
    assert org.slug == "solo"


def tests_create_personal_organization_slug_is_unique():
    # Distinct usernames that slugify to the same base ("dup").
    first = test_helpers.create_User(username="dup")
    second = test_helpers.create_User(username="Dup")
    org1 = create_personal_organization(first)
    org2 = create_personal_organization(second)
    assert org1.slug == "dup"
    assert org2.slug == "dup-2"


# --- role permissions -------------------------------------------------------

def tests_role_rank_ordering():
    assert (
        role_rank(Membership.Role.OWNER)
        > role_rank(Membership.Role.ADMIN)
        > role_rank(Membership.Role.MEMBER)
        > role_rank(Membership.Role.VIEWER)
    )
    assert role_rank("nonsense") == 0


def tests_has_role_respects_precedence():
    org = test_helpers.create_organizations_Organization()
    owner = test_helpers.create_User()
    viewer = test_helpers.create_User()
    stranger = test_helpers.create_User()
    test_helpers.create_organizations_Membership(
        user=owner, organization=org, role=Membership.Role.OWNER
    )
    test_helpers.create_organizations_Membership(
        user=viewer, organization=org, role=Membership.Role.VIEWER
    )

    # Owner clears the member bar; viewer does not; stranger fails entirely.
    assert has_role(owner, org, Membership.Role.MEMBER)
    assert not has_role(viewer, org, Membership.Role.MEMBER)
    assert has_role(viewer, org, Membership.Role.VIEWER)
    assert not has_role(stranger, org, Membership.Role.VIEWER)


def tests_has_role_false_for_anonymous():
    from django.contrib.auth.models import AnonymousUser

    org = test_helpers.create_organizations_Organization()
    assert not has_role(AnonymousUser(), org, Membership.Role.VIEWER)


def tests_require_role_mixin_blocks_insufficient_role(rf):
    from django.core.exceptions import PermissionDenied

    org = test_helpers.create_organizations_Organization()
    viewer = test_helpers.create_User()
    test_helpers.create_organizations_Membership(
        user=viewer, organization=org, role=Membership.Role.VIEWER
    )

    class _View(RequireRoleMixin):
        required_role = Membership.Role.MEMBER

        def get_organization(self):
            return org

        def get(self, request):  # pragma: no cover - reached only if allowed
            from django.http import HttpResponse

            return HttpResponse("ok")

    request = rf.get("/")
    request.user = viewer
    with pytest.raises(PermissionDenied):
        _View().dispatch(request)


# --- active-org switch view -------------------------------------------------

def tests_switch_view_sets_active_org(client):
    user = test_helpers.create_User()
    a = test_helpers.create_organizations_Organization(name="Alpha")
    b = test_helpers.create_organizations_Organization(name="Bravo")
    test_helpers.create_organizations_Membership(user=user, organization=a)
    test_helpers.create_organizations_Membership(user=user, organization=b)
    client.force_login(user)

    response = client.post(reverse("organizations:switch"), {"organization": b.pk})
    assert response.status_code == 302
    assert client.session[SESSION_KEY] == b.pk


def tests_switch_view_rejects_non_member_org(client):
    user = test_helpers.create_User()
    mine = test_helpers.create_organizations_Organization(name="Mine")
    theirs = test_helpers.create_organizations_Organization(name="Theirs")
    test_helpers.create_organizations_Membership(user=user, organization=mine)
    client.force_login(user)
    client.post(reverse("organizations:switch"), {"organization": mine.pk})

    response = client.post(
        reverse("organizations:switch"), {"organization": theirs.pk}
    )
    assert response.status_code == 404
    # Session unchanged: still pointing at the org the user belongs to.
    assert client.session[SESSION_KEY] == mine.pk


def tests_switch_view_requires_login(client):
    response = client.post(reverse("organizations:switch"), {"organization": 1})
    assert response.status_code == 302
    assert reverse("login") in response.url


def tests_switch_view_rejects_get(client):
    user = test_helpers.create_User()
    client.force_login(user)
    response = client.get(reverse("organizations:switch"))
    assert response.status_code == 405


# --- get_active_organization fallback ---------------------------------------

def tests_get_active_organization_falls_back_to_first(rf):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization()
    test_helpers.create_organizations_Membership(user=user, organization=org)
    request = rf.get("/")
    request.user = user
    request.session = {}

    active = get_active_organization(request)
    assert active == org
    assert request.session[SESSION_KEY] == org.pk


def tests_get_active_organization_ignores_stale_id(rf):
    user = test_helpers.create_User()
    left = test_helpers.create_organizations_Organization(name="Left")
    current = test_helpers.create_organizations_Organization(name="Current")
    test_helpers.create_organizations_Membership(user=user, organization=current)
    request = rf.get("/")
    request.user = user
    # Session points at an org the user is not a member of.
    request.session = {SESSION_KEY: left.pk}

    active = get_active_organization(request)
    assert active == current
    assert request.session[SESSION_KEY] == current.pk


def tests_get_active_organization_none_without_membership(rf):
    user = test_helpers.create_User()
    request = rf.get("/")
    request.user = user
    request.session = {}
    assert get_active_organization(request) is None


# --- projects ---------------------------------------------------------------

def _logged_in_member(client, role=Membership.Role.MEMBER):
    """User in a fresh org (with ``role``), logged in, with that org active."""
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


def tests_project_list_shows_only_active_org_projects(client):
    user, org = _logged_in_member(client)
    mine = test_helpers.create_organizations_Project(
        organization=org, name="Mine"
    )
    theirs = test_helpers.create_organizations_Project(name="Theirs")
    response = client.get(reverse("organizations:Project_list"))
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert mine.name in body
    assert theirs.name not in body


def tests_project_detail_lists_its_tasks(client):
    user, org = _logged_in_member(client)
    project = test_helpers.create_organizations_Project(organization=org)
    task = test_helpers.create_tasks_Task(
        owner=user, project=project, title="proj-task"
    )
    response = client.get(
        reverse("organizations:Project_detail", args=[project.pk])
    )
    assert response.status_code == 200
    assert "proj-task" in response.content.decode("utf-8")


def tests_project_detail_other_org_404(client):
    _logged_in_member(client)
    foreign = test_helpers.create_organizations_Project()
    response = client.get(
        reverse("organizations:Project_detail", args=[foreign.pk])
    )
    assert response.status_code == 404


def tests_project_create_requires_member_role(client):
    _logged_in_member(client, role=Membership.Role.VIEWER)
    assert client.get(reverse("organizations:Project_create")).status_code == 403


def tests_project_create_attaches_to_active_org(client):
    user, org = _logged_in_member(client)
    response = client.post(
        reverse("organizations:Project_create"),
        {"name": "Roadmap", "description": "Q3 work"},
    )
    assert response.status_code == 302
    project = Project.objects.get(name="Roadmap")
    assert project.organization == org


# --- project types (seeded) -------------------------------------------------

def tests_seeded_project_types_exist():
    software = ProjectType.objects.get(name="Software Tasks")
    fields = {f.name: f for f in software.field_definitions.all()}
    assert fields["priority"].field_type == FieldDefinition.FieldType.CHOICE
    assert fields["priority"].required
    assert fields["priority"].choices == ["Low", "Medium", "High"]
    assert "component" in fields

    translation = ProjectType.objects.get(name="Translation Jobs")
    names = {f.name for f in translation.field_definitions.all()}
    assert {"source_lang", "target_lang", "word_count", "deadline"} <= names


def tests_seeded_status_workflows_exist():
    software = ProjectType.objects.get(name="Software Tasks")
    statuses = list(software.status_definitions.all())
    assert [s.name for s in statuses] == [
        "backlog", "in_progress", "in_review", "done",
    ]
    assert statuses[0].is_default
    assert statuses[-1].is_terminal

    translation = ProjectType.objects.get(name="Translation Jobs")
    names = [s.name for s in translation.status_definitions.all()]
    assert names == ["new", "translating", "review", "delivered"]


def tests_switching_project_type_preserves_data_and_revalidates():
    type_a = test_helpers.create_organizations_ProjectType(name="A")
    test_helpers.create_organizations_FieldDefinition(
        project_type=type_a, name="fa",
        field_type=FieldDefinition.FieldType.TEXT, required=True,
    )
    type_b = test_helpers.create_organizations_ProjectType(name="B")
    test_helpers.create_organizations_FieldDefinition(
        project_type=type_b, name="fb",
        field_type=FieldDefinition.FieldType.TEXT, required=True,
    )
    project = test_helpers.create_organizations_Project(project_type=type_a)
    task = test_helpers.create_tasks_Task(
        project=project, custom_fields={"fa": "kept"}
    )

    project.project_type = type_b
    project.save()
    task.refresh_from_db()
    # Existing task data is preserved, not rewritten.
    assert task.custom_fields == {"fa": "kept"}
    # New validation uses the new type's schema.
    assert validate_custom_fields(project.project_type, {"fb": "y"}) == {"fb": "y"}
    with pytest.raises(Exception):
        validate_custom_fields(project.project_type, {"fa": "x"})


# --- context processor ------------------------------------------------------

def tests_context_processor_exposes_active_and_user_orgs(client):
    user = test_helpers.create_User()
    org = test_helpers.create_organizations_Organization(name="Ctx Org")
    test_helpers.create_organizations_Membership(user=user, organization=org)
    client.force_login(user)

    response = client.get(reverse("tasks:Task_list"))
    assert response.context["active_organization"] == org
    assert list(response.context["user_organizations"]) == [org]
    # Switcher renders the org name in the nav.
    assert "Ctx Org" in response.content.decode("utf-8")
