<h1 align="center">TaskBoard</h1>

<p align="center">
  A multi-tenant work platform built on Django — organizations, projects, and
  typed tasks with custom fields and workflows, server-rendered pages plus a
  documented REST API.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/Django-6.0.5-092E20?logo=django&logoColor=white" alt="Django 6.0.5">
  <img src="https://img.shields.io/badge/DRF-3.17-A30000?logo=django&logoColor=white" alt="Django REST Framework 3.17">
  <img src="https://img.shields.io/badge/DB-SQLite%20%2F%20Postgres-003B57?logo=postgresql&logoColor=white" alt="SQLite / Postgres">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker ready">
  <img src="https://github.com/abdulwahed-sweden/TaskBoard/actions/workflows/ci.yml/badge.svg" alt="CI">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

---

TaskBoard manages **any kind of work** — software tasks, translation jobs,
support tickets — without writing new code per domain. A generic work item
(`Task`) takes its shape from a **project type** that declares custom fields and
a status workflow. It was grown from a single-user task list into a team
platform over ten phases (see [`ROADMAP.md`](ROADMAP.md)).

## Features

- **Organizations & membership** — multi-tenant: users belong to organizations
  with a role (`owner` › `admin` › `member` › `viewer`) and switch the active
  org in the nav. A personal org is created on signup.
- **Projects** — work lives in projects inside an organization. Access is
  **membership-scoped** (you see work in your orgs; viewers are read-only) — not
  owner-scoped.
- **Project types & custom fields** — a `ProjectType` declares a custom-field
  schema (text/number/date/choice/boolean); each task stores validated
  `custom_fields`. Two types are seeded (Software Tasks, Translation Jobs).
- **Status workflows** — statuses are defined per project type; `is_done` is
  derived from terminal statuses.
- **Collaboration** — comments and an append-only activity log
  (created / updated / status-change / assignment); tasks have an editable
  assignee.
- **CSV / XLSX import** — upload → map columns → preview validation → commit
  (invalid rows reported, not dropped); reuses the same field validators.
- **REST API** — token auth, filtering / ordering / pagination, and an OpenAPI
  schema with Swagger UI & ReDoc — all org/project-scoped.
- **Email notifications** — assignees are notified on assignment, comments, and
  status changes, with per-user preferences.
- **Dashboards & saved views** — an org dashboard (counts, overdue, recent
  activity) and named, shared, per-project task-list filters.
- **Production-ready** — Postgres via `DATABASE_URL`, Docker + compose,
  WhiteNoise static serving, gunicorn, env-driven security, and CI.

---

## Quick start (development)

```bash
git clone https://github.com/abdulwahed-sweden/TaskBoard.git
cd TaskBoard

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

python manage.py migrate          # SQLite by default
python manage.py createsuperuser
python manage.py runserver        # http://127.0.0.1:8000
```

## Run with Docker (Postgres)

```bash
docker compose up --build         # app on http://localhost:8000, against Postgres 16
```

The `web` container runs migrations and `collectstatic`, then serves via
gunicorn; the `db` service is Postgres with a healthcheck and a persistent
volume.

---

## Pages & endpoints

| Page / endpoint        | URL                          | Notes                                    |
|------------------------|------------------------------|------------------------------------------|
| **Home**               | `/`                          | Landing page                             |
| **Sign up / Log in**   | `/accounts/signup/`, `/accounts/login/` | Login has a "Forgot password?" link |
| **Profile**            | `/accounts/profile/`         | Account + your tasks                     |
| **Notifications**      | `/accounts/notifications/`   | Per-user email preferences               |
| **Dashboard**          | `/tasks/dashboard/`          | Active-org counts, overdue, activity     |
| **Projects**           | `/organizations/projects/`   | Projects in the active org               |
| **Tasks**              | `/tasks/Task/`               | Filter by project/status/done/search     |
| **Import**             | `/tasks/import/`             | CSV / XLSX importer (members+)           |
| **Admin**              | `/admin/`                    | Django admin (branded to match)          |
| **API**                | `/tasks/api/v1/`             | DRF, token or session auth               |
| **API token**          | `/api/token/`                | POST username+password → token           |
| **API docs**           | `/api/docs/` · `/api/redoc/` | Swagger UI / ReDoc (`/api/schema/`)      |

---

## REST API

Authenticate with a token or a session:

```bash
# Get a token
curl -s -X POST http://localhost:8000/api/token/ \
  -d "username=you&password=secret"            # -> {"token": "..."}

# Use it (results are paginated + scoped to your organizations)
curl -s http://localhost:8000/tasks/api/v1/Task/?ordering=due_date \
  -H "Authorization: Token <token>"
```

List endpoints support `?project=`, `?is_done=`, `?status=`, `?ordering=`, and
`?search=`. Explore the full schema at `/api/docs/`.

---

## Configuration

Settings read from the environment with development fallbacks.

| Variable                     | Default (dev)            | Notes                                  |
|------------------------------|--------------------------|----------------------------------------|
| `DJANGO_SECRET_KEY`          | insecure dev key         | **Required** in production             |
| `DJANGO_DEBUG`               | `True`                   | Set to `False` in production           |
| `DJANGO_ALLOWED_HOSTS`       | empty                    | Comma-separated, e.g. `a.com,b.com`    |
| `DATABASE_URL`               | SQLite                   | e.g. `postgres://user:pass@host/db`    |
| `DJANGO_CSRF_TRUSTED_ORIGINS`| empty                    | e.g. `https://app.example.com`         |
| `DJANGO_EMAIL_BACKEND`       | console                  | Notification/reset mail prints to stdout in dev |
| `DJANGO_EMAIL_*`             | localhost SMTP           | `HOST` / `PORT` / `USE_TLS` / `HOST_USER` / `HOST_PASSWORD` |
| `DJANGO_DEFAULT_FROM_EMAIL`  | `taskboard@example.com`  | "From" address on outgoing mail        |

When `DEBUG=False`, TLS security settings (SSL redirect, secure cookies, HSTS,
proxy SSL header) switch on automatically and are each env-overridable for a
non-TLS deployment.

---

## Testing

```bash
pytest                              # full suite (SQLite)
pytest tests/tasks/test_views.py    # one file
pytest -k import                    # by keyword

python manage.py check              # sanity check
python manage.py check --deploy     # production readiness (clean with DEBUG=False + ALLOWED_HOSTS)
```

CI (GitHub Actions) runs `pytest` + `manage.py check --deploy` on every push and
pull request.

---

## Project layout

```
TaskBoard/
├── manage.py
├── Dockerfile · entrypoint.sh · docker-compose.yml   # containerized deploy
├── .github/workflows/ci.yml                          # CI: pytest + check --deploy
├── requirements.txt / requirements-dev.txt
├── TaskBoard/                  # project package: settings (env-driven), urls, views
├── organizations/             # tenancy: Organization, Membership, Project,
│                              #   ProjectType, FieldDefinition, StatusDefinition
│                              #   + custom-field / workflow validators
├── tasks/                     # the work item: Task, Comment, Activity,
│                              #   NotificationPreference, SavedView; views, DRF API,
│                              #   importer, notifications, activity log
├── templates/                 # base.html, registration/, admin/ override
└── tests/                     # pytest suite (organizations/ + tasks/)
```

See [`CLAUDE.md`](CLAUDE.md) for the full architecture and conventions.

---

## Tech stack

**Python 3.12+** · **Django 6** · **Django REST Framework** (token auth,
django-filter, drf-spectacular) · **SQLite** (dev) / **Postgres** (prod, via
dj-database-url + psycopg3) · **gunicorn + WhiteNoise** · **Docker** · **pytest**

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE).
