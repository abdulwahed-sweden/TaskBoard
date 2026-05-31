# CLAUDE.md

Guidance for AI coding assistants (and humans) working in this repository.
Read this before making changes.

## Project overview

**TaskBoard** is a small Django web application for managing tasks. It exposes
both server-rendered pages (Django class-based views + templates) and a REST
API (Django REST Framework). It was originally scaffolded with Django Builder
and has since been upgraded to Django 6 and cleaned up.

It is being evolved into a multi-tenant work platform (see `ROADMAP.md`).
**Phase 1 (organizations & membership) has landed:** users belong to
organizations, with a per-session "active org." Tasks are still owner-scoped for
now — moving them under organizations/projects is Phase 2.

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
├── organizations/            # multi-tenancy: orgs, memberships, active-org
│   ├── models.py             # Organization, Membership (+ Role, role_rank)
│   ├── services.py           # create_personal_organization (shared w/ migration)
│   ├── permissions.py        # has_role, RequireRoleMixin
│   ├── sessions.py           # active-org session helpers
│   ├── context_processors.py # exposes active_organization / user_organizations
│   ├── views.py              # SwitchOrganizationView
│   ├── urls.py               # /organizations/switch/
│   ├── admin.py              # Organization + Membership admin
│   └── migrations/           # 0001 models, 0002 personal orgs for existing users
├── tasks/                    # the work-item app
│   ├── models.py             # Task model
│   ├── views.py              # class-based views
│   ├── api.py                # DRF viewset
│   ├── serializers.py        # DRF serializer
│   ├── forms.py              # ModelForm
│   ├── admin.py              # admin registration
│   ├── urls.py               # app urlconf (web + api routes)
│   ├── migrations/
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
  `Membership` ad hoc. Task views are **not** org-scoped yet — that arrives in
  Phase 2; today they remain owner-scoped (see Web layer below).

### The `Task` model
`tasks/models.py` defines a single `Task` with: `owner` (FK to `auth.User`,
nullable), `title`, `notes`, `is_done`, `due_date`, plus auto-managed `created`
and `last_updated` timestamps. Default ordering is newest-first (`-created`).
The model also exposes `get_absolute_url`, `get_update_url`, `get_delete_url`
and a static `get_create_url`, which the templates rely on — keep these in sync
with the URL names in `tasks/urls.py` if you rename routes.

### Web layer
Plain Django generic class-based views (`ListView`, `CreateView`, `DetailView`,
`UpdateView`, `DeleteView`) in `tasks/views.py`. Create/Update use
`forms.TaskForm`. Templates live in `tasks/templates/tasks/` and extend
`templates/base.html`.

**Task views require login and are owner-scoped.** All task views use
`LoginRequiredMixin`; the read/update/delete views go through `OwnedTasksMixin`,
which filters the queryset to `owner=request.user` (so another user's task 404s
rather than leaking). `TaskCreateView.form_valid` sets `owner` to the logged-in
user, so `owner` is intentionally **not** a `TaskForm` field.

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
DRF `ModelViewSet` (`tasks/api.py`) registered on a `DefaultRouter` under
`/tasks/api/v1/`. **The API requires authentication** (`IsAuthenticated`), so
unauthenticated requests correctly return `403`. The serializer
(`tasks/serializers.py`) currently exposes all model fields.

### URL names
App namespace is `tasks`. Reverse routes as `tasks:Task_list`,
`tasks:Task_create`, `tasks:Task_detail`, `tasks:Task_update`,
`tasks:Task_delete`.

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
  `create_organizations_Membership`). Reuse them in new tests instead of
  building objects inline. Tests live under `tests/<app>/` (e.g.
  `tests/tasks/`, `tests/organizations/`).
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
- **The serializer exposes every field, including timestamps.** Tighten
  `fields`/add `read_only_fields` before exposing the API publicly.
