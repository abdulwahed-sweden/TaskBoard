# CLAUDE.md

Guidance for AI coding assistants (and humans) working in this repository.
Read this before making changes.

## Project overview

**TaskBoard** is a small Django web application for managing tasks. It exposes
both server-rendered pages (Django class-based views + templates) and a REST
API (Django REST Framework). It was originally scaffolded with Django Builder
and has since been upgraded to Django 6 and cleaned up.

The codebase is intentionally small. Prefer keeping it that way: add behaviour
where it belongs rather than introducing new layers or abstractions.

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
├── tasks/                    # the single app
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
└── tests/tasks/test_views.py
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
  `create_User`). Reuse them in new tests instead of building objects inline.
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
