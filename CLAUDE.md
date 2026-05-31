# CLAUDE.md

Guidance for AI coding assistants (and humans) working in this repository.
Read this before making changes.

## Project overview

**TaskBoard** is a small Django web application for managing tasks. It exposes
both server-rendered pages (Django class-based views + templates) and a REST
API (Django REST Framework). It was originally scaffolded with Django Builder
and has since been upgraded to Django 6 and cleaned up.

It is being evolved into a multi-tenant work platform (see `ROADMAP.md`).
**Phases 1–5 have landed:** users belong to organizations (with a per-session
"active org"), organizations contain projects, and every task lives in a
project. Task access is **membership-scoped** — you see/act on tasks in projects
inside orgs you belong to, gated by role (viewers are read-only). A project may
have a **`ProjectType`** that declares a custom-field schema and an ordered
**status workflow**; each task carries validated domain data in a
`custom_fields` JSONField and a workflow `status` (with `is_done` auto-synced
from terminal statuses). Tasks support **comments** and an append-only
**activity log** (created/updated/status-change/assignment), and `owner` is an
editable **assignee**. Phase 6 (data import) is next.

The codebase is intentionally small. Prefer keeping it that way: add behaviour
where it belongs rather than introducing new layers or abstractions. Tenancy
concerns live in the dedicated `organizations` app; the `tasks` app stays
focused on the work item itself.

## Tech stack

- Python 3.12+
- Django 6.0.5
- Django REST Framework 3.17+
- SQLite (development default; swap via `DATABASES` for production)
- pytest + pytest-django for tests

## Repository layout

```
TaskBoard/
├── manage.py
├── requirements.txt          # runtime deps
├── requirements-dev.txt      # test/dev deps
├── pytest.ini                # pytest config (uses test_settings)
├── test_settings.py          # imports * from TaskBoard.settings
├── test_helpers.py           # factory-style helpers for tests
├── TaskBoard/                # project (settings) package
│   ├── settings.py
│   ├── urls.py               # root urlconf
│   ├── wsgi.py / asgi.py
│   └── consumers.py / routing.py   # Channels stubs (unused, see "Known quirks")
├── organizations/            # multi-tenancy + project types
│   ├── models.py             # Organization, Membership, Project, ProjectType, FieldDefinition, StatusDefinition
│   ├── services.py           # create_personal_organization (shared w/ migration)
│   ├── permissions.py        # has_role, RequireRoleMixin
│   ├── custom_fields.py      # validate_custom_fields (form + API + import reuse it)
│   ├── workflow.py           # validate_status / default_status / is_terminal_status
│   ├── sessions.py           # active-org session helpers
│   ├── context_processors.py # exposes active_organization / user_organizations
│   ├── views.py              # SwitchOrganizationView, ActiveOrganizationMixin, Project views
│   ├── urls.py               # /organizations/switch/, /organizations/projects/...
│   ├── admin.py              # Organization/Membership/Project/ProjectType admin
│   ├── templates/organizations/  # project_list / project_detail / project_form
│   └── migrations/           # ...0004 ProjectType, 0005 seed types, 0006 StatusDefinition, 0007 seed workflows
├── tasks/                    # the work-item app (membership-scoped)
│   ├── models.py             # Task, Comment, Activity
│   ├── activity.py           # log_created / log_changes / snapshot (activity log)
│   ├── views.py              # CBVs: OrgScopedTaskMixin, TaskWriteRoleMixin, AddCommentView
│   ├── api.py                # DRF Task + Project viewsets (org-scoped)
│   ├── serializers.py        # DRF serializers
│   ├── forms.py              # TaskForm (project/assignee/custom/status-aware), CommentForm
│   ├── admin.py              # Task / Comment / Activity admin
│   ├── urls.py               # app urlconf (web + api routes)
│   ├── migrations/           # ...0005 custom_fields, 0006 status, 0007 Comment+Activity
│   └── templates/tasks/      # task_list / task_detail / task_form / task_confirm_delete
├── templates/                # project-level templates (base.html, index.html, htmx/)
└── tests/                    # tests/tasks/ and tests/organizations/
```

## Common commands

Run everything from the repository root (where `manage.py` lives).

```bash
# First-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Database
python manage.py makemigrations
python manage.py migrate

# Run the dev server
python manage.py runserver          # http://127.0.0.1:8000

# Create an admin user (needed to reach /admin/ and the authenticated API)
python manage.py createsuperuser

# Tests
pytest                              # all tests
pytest tests/tasks/test_views.py    # a single file
pytest -k create                    # by keyword

# Sanity / deploy checks
python manage.py check
python manage.py check --deploy     # run before shipping to production
```

## Architecture & conventions

### Organizations & membership (multi-tenancy)
The `organizations` app holds the tenancy layer.

- **Models** (`organizations/models.py`): `Organization` (name + unique `slug`)
  and `Membership` (user ⇄ org with a `role`). Roles are a `TextChoices` enum —
  `owner` > `admin` > `member` > `viewer` — and `ROLE_RANK` / `role_rank()`
  encode that precedence. `(user, organization)` is unique.
- **Personal org on signup**: `SignUpView.form_valid` (in `TaskBoard/views.py`)
  calls `organizations.services.create_personal_organization(user)`, which makes
  an org and an `owner` membership. The same logic is mirrored in data migration
  `0002_create_personal_orgs` for users that predate the feature (migrations use
  historical models and cannot import the service).
- **Active organization**: stored in the session as `active_organization_id`.
  Always read it through `organizations.sessions.get_active_organization(request)`,
  which validates membership and falls back to the user's first org (so a stale
  or tampered id can never leak another tenant). `context_processors.organizations`
  exposes `active_organization` and `user_organizations` to every template, and
  `base.html` renders an org switcher that POSTs to `SwitchOrganizationView`
  (`organizations:switch`, POST-only, member-checked).
- **Permission helpers** (`organizations/permissions.py`): `has_role(user, org,
  min_role)` predicate and `RequireRoleMixin` (set `required_role`, implement
  `get_organization()`) for gating views by role. Use these instead of querying
  `Membership` ad hoc.
- **Projects** (`organizations/models.py` `Project`): a named container for work
  inside an org (`organization` FK, `name`, `description`; name unique per org).
  Every `Task` belongs to a project. `ActiveOrganizationMixin` (in
  `organizations/views.py`) resolves `self.active_organization` and, if
  `required_role` is set, enforces it. `ProjectListView` (active-org projects),
  `ProjectDetailView` (org-scoped; lists the project's tasks),
  `ProjectCreateView` (members+; routes `organizations:Project_list` /
  `_detail` / `_create`). Project edit/delete is admin-only for now.
- **Project types & custom fields** (`ProjectType`, `FieldDefinition`): a
  project may set `project_type` (nullable FK, `PROTECT`). A type owns ordered
  `FieldDefinition`s (`name`, `label`, `field_type` ∈ text/number/date/choice/
  boolean, `required`, `choices`) — the schema for `Task.custom_fields`.
  **`organizations/custom_fields.validate_custom_fields(project_type, raw)` is
  the single source of truth**: rejects unknown keys, enforces required, checks
  & normalizes types (dates → ISO strings), and an untyped project permits only
  empty custom fields. It is reused by `TaskForm`, the serializer, and (later)
  the importer. Two types are seeded by migration (Software Tasks, Translation
  Jobs); add/edit types via the admin (`ProjectType` with a `FieldDefinition`
  inline). Switching a project's type does **not** rewrite existing tasks'
  stored data — values are preserved and only re-validated on the next edit.
- **Status workflows** (`StatusDefinition`): a `ProjectType` also owns ordered
  statuses (`name`, `label`, `order`, `is_default`, `is_terminal`).
  **`organizations/workflow.validate_status(project_type, status)` is the single
  source of truth**: a typed task's status must be one of the type's statuses
  (empty resolves to the default); an untyped project (no statuses) requires an
  empty status. Any status in the set is allowed — no transition restrictions
  yet. `is_done` is **derived**: `Task.save()` sets it from whether the status
  is terminal (for typed projects); untyped projects edit `is_done` directly.
  Two workflows are seeded (Software Tasks: Backlog→…→Done; Translation Jobs:
  New→…→Delivered); edit via the `StatusDefinition` admin inline.

### The `Task` model
`tasks/models.py` defines `Task` with: `project` (FK to `organizations.Project`,
**required** — every task lives in a project), `owner` (FK to `auth.User`,
nullable — the **assignee**, editable; defaults to the creator), `title`,
`notes`, `is_done`, `status` (CharField, validated against the project type's
workflow), `due_date`, `custom_fields` (JSONField, validated against the project
type), plus auto-managed `created`/`last_updated` timestamps. Default ordering is
newest-first (`-created`). `Task.clean()` validates `custom_fields` and `status`
(attaching errors to those fields, for the admin/raw path) unless
`_skip_custom_field_validation` is set — `TaskForm` sets that because it
validates onto its own widgets. `Task.save()` keeps `is_done` in sync with a
terminal status. `status_label` returns the human label. The model exposes
`get_absolute_url`, `get_update_url`, `get_delete_url` and a static
`get_create_url`, which the templates rely on — keep these in sync with
`tasks/urls.py` if you rename routes.

### Collaboration: comments & activity
`Comment` (task, author, body, created) is discussion on a task; `Activity` is an
**append-only** log of lifecycle events (`created`, `updated`, `status_changed`,
`assigned`) with an optional `detail` JSON (e.g. `{"from","to"}`).
**`tasks/activity.py` records activity from the app's write paths** — `snapshot`
captures (status, owner) before a save; `log_created`/`log_changes` are called
from `TaskCreateView`/`TaskUpdateView` (web) and `TaskViewSet.perform_create`/
`perform_update` (API). Admin/raw ORM saves intentionally don't log. Both are
surfaced on the task detail page; `Activity` admin is read-only (append-only).
Posting a comment (`AddCommentView`, route `tasks:Task_comment`) is org-scoped
and requires `member`+ (viewers can read but not comment).

### Web layer
Plain Django generic class-based views (`ListView`, `CreateView`, `DetailView`,
`UpdateView`, `DeleteView`) in `tasks/views.py`. Create/Update use
`forms.TaskForm` (which takes a `projects` queryset and an `assignees` queryset
limiting the selectable project and owner; **dynamically adds one `custom_<name>`
field per the project type's `FieldDefinition`s**; and for a typed project swaps
the `is_done` checkbox for a required `status` dropdown driven by the type's
workflow — all render via `{{ form.as_div }}`). The target project is the
submitted one when bound, else the instance/initial — so without JS, changing
the project dropdown re-renders the right custom fields on submit. Templates
live in `tasks/templates/tasks/` and extend `templates/base.html`.

**Task views require login and are membership-scoped** (this replaced the old
owner-scoping in Phase 2):
- `OrgScopedTaskMixin.get_queryset()` filters to
  `project__organization__members=request.user` — the read boundary, so a task
  in another org 404s on detail/update/delete rather than leaking.
- `TaskListView` (via `ActiveOrganizationMixin`) shows tasks in the **active
  org**, with an optional `?project=<id>` filter (constrained to the active org).
- Writes require `member`+: `TaskCreateView` gates on the active org and
  defaults `owner` to the request user only when the assignee field is left
  blank; `TaskUpdateView`/`TaskDeleteView`/`AddCommentView` use
  `TaskWriteRoleMixin` (or an equivalent check), which 403s if the user lacks
  `member` in the task's org (so a `viewer` can read the detail page and
  comments but not edit/delete/comment).

### Accounts & profile
Authentication uses Django's built-in views, wired in `TaskBoard/urls.py`:
`django.contrib.auth.urls` provides `login`/`logout`, `password_change`
(+ `_done`) and the password-reset flow, and project-level views in
`TaskBoard/views.py` add `signup` (`UserCreationForm`) and `profile` (an
`UpdateView` on the current `User` that also lists their tasks). Auth
templates live in `templates/registration/`. `settings.py` sets `LOGIN_URL`,
`LOGIN_REDIRECT_URL` (→ task list) and `LOGOUT_REDIRECT_URL` (→ index).
Logout is POST-only (Django 5+), so the nav uses a small form.

### Password reset & email
"Forgot password?" (linked from the login page) uses Django's
`PasswordReset*` views. The page templates plus the message body
(`password_reset_email.html`) and subject (`password_reset_subject.txt`)
live in `templates/registration/`. Email is configured in `settings.py`
from the environment with dev fallbacks: `EMAIL_BACKEND` defaults to the
**console backend** (reset messages print to the runserver stdout — no real
mail is sent in dev). For production set `DJANGO_EMAIL_BACKEND` and the
`DJANGO_EMAIL_*`/`DJANGO_DEFAULT_FROM_EMAIL` SMTP variables. In tests, assert
delivery via pytest-django's `mailoutbox` fixture.

### API layer
DRF viewsets (`tasks/api.py`) — `TaskViewSet` and `ProjectViewSet` — registered
on a `DefaultRouter` under `/tasks/api/v1/` (basenames `task`/`project`; reverse
as `tasks:task-list`, `tasks:task-detail`, etc.). **The API requires
authentication**, so unauthenticated requests return `403`. Both viewsets are
**org-scoped**: `get_queryset()` filters to objects in orgs the user belongs to
(never `.all()`), so foreign objects 404. The `IsOrgMemberForWrites` permission
makes writes require `member` in the object's org (reads need `viewer`), and the
serializers reject filing a task/project into an org the user can't write to.
`owner` (assignee) is **writable** but defaults to the request user on create
(`perform_create`); a supplied owner is validated to be a member of the
project's org. `created`/`last_updated` are read-only. `TaskSerializer` exposes
`custom_fields` and `status` and validates them (via the shared
`validate_custom_fields` / `validate_status`) whenever the `project`,
`custom_fields`, or `status` changes; `is_done` is derived on save (read-driven
for typed tasks). `perform_create`/`perform_update` record activity (see
Collaboration).

### URL names
App namespace is `tasks`. Web routes: `tasks:Task_list`, `tasks:Task_create`,
`tasks:Task_detail`, `tasks:Task_update`, `tasks:Task_delete`,
`tasks:Task_comment`. API routes
(router): `tasks:task-list`/`tasks:task-detail`,
`tasks:project-list`/`tasks:project-detail`. Project web routes live in the
`organizations` namespace: `organizations:Project_list` / `_detail` / `_create`
and `organizations:switch`.

## Configuration

`settings.py` reads sensitive/environment-specific values from the environment
with development fallbacks:

| Variable               | Default (dev)        | Notes                                |
|------------------------|----------------------|--------------------------------------|
| `DJANGO_SECRET_KEY`    | insecure dev key     | **Must** be set in production         |
| `DJANGO_DEBUG`         | `True`               | Set to `False` in production          |
| `DJANGO_ALLOWED_HOSTS` | empty                | Comma-separated list, e.g. `a.com,b.com` |

For a real deployment: set the variables above, switch `DATABASES` to Postgres,
configure static file serving, and run `manage.py check --deploy`.

## Testing notes

- pytest is configured via `pytest.ini` and uses `test_settings` (which simply
  re-exports `TaskBoard.settings`). Override test-only settings there.
- `test_helpers.py` holds small factory functions (e.g. `create_tasks_Task`,
  `create_User`, `create_organizations_Organization`,
  `create_organizations_Membership`, `create_organizations_Project`,
  `create_organizations_ProjectType`, `create_organizations_FieldDefinition`,
  `create_organizations_StatusDefinition`, `create_tasks_Comment`). Reuse them in
  new tests instead of building objects inline. The shared validators have
  focused tests in `tests/organizations/test_custom_fields.py` and
  `tests/organizations/test_workflow.py`; activity recording in
  `tests/tasks/test_activity.py`. Tests live under
  `tests/<app>/` (e.g. `tests/tasks/`, `tests/organizations/`). Note
  `create_tasks_Task` auto-creates a project (and, for a real owner, an org
  membership) when none is passed, so the task is visible under org-scoping;
  pass an explicit `project=` to control which org a task lands in. For API
  tests use `rest_framework.test.APIClient` with `force_authenticate`.
- Tests that touch the database must be marked — the existing module sets
  `pytestmark = [pytest.mark.django_db]` at the top; follow that pattern.
- Keep views side-effect free beyond their HTTP responsibilities so they stay
  easy to test.

## Conventions for changes

- Follow PEP 8 and the existing style; use clear, domain-specific names.
- After changing a model, always generate and commit a migration
  (`makemigrations`) — never hand-edit applied migrations.
- Add or update a test for any behavioural change; run `pytest` before finishing.
- Catch specific exceptions, never bare `except`. Use the `logging` module
  rather than `print` for diagnostics.
- Don't add new dependencies or architectural layers unless they clearly earn
  their place.

## Known quirks

- **Channels stubs are unused.** `TaskBoard/consumers.py`, `routing.py`, and the
  per-app `tasks/consumers.py` were generated but nothing is wired up (the app
  runs over WSGI). Safe to ignore or delete if you're not adding websockets.
- **`htmx/` templates are unused.** `templates/htmx/*` were scaffolded but the
  project does not use htmx. Remove them if you want a leaner template tree.
- **Fallback "Unassigned" org.** The Phase 2 task backfill
  (`tasks/migrations/0003`) parks tasks with no owner (or whose owner had no
  membership) in a memberless `Unassigned` organization so the `project` FK can
  be non-null. Those tasks are intentionally invisible until an admin reassigns
  them — mirroring how null-owner tasks were invisible under the old scoping.
