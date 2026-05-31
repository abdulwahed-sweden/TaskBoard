<h1 align="center">TaskBoard</h1>

<p align="center">
  A small, clean Django app for managing tasks — server-rendered pages plus a REST API.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/Django-6.0.5-092E20?logo=django&logoColor=white" alt="Django 6.0.5">
  <img src="https://img.shields.io/badge/DRF-3.17-A30000?logo=django&logoColor=white" alt="Django REST Framework 3.17">
  <img src="https://img.shields.io/badge/Tests-pytest-0A9EDC?logo=pytest&logoColor=white" alt="pytest">
  <img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

---

## Features

- **Tasks** — create, view, edit, and delete tasks with title, notes, done flag, and due date.
- **Accounts** — sign up, log in / log out, and a profile page.
- **Owner-scoped** — every task belongs to its creator; you only ever see your own.
- **Password management** — change password, plus a full "forgot password" reset flow.
- **HTML email** — branded, styled password-reset messages (plain-text fallback included).
- **REST API** — authenticated CRUD endpoints under `/tasks/api/v1/`.
- **Clean UI** — a self-contained design system, no CSS framework dependency.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/abdulwahed-sweden/TaskBoard.git
cd TaskBoard

# 2. Set up a virtual environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 3. Set up the database
python manage.py migrate

# 4. Create an admin user
python manage.py createsuperuser

# 5. Run it
python manage.py runserver        # http://127.0.0.1:8000
```

---

## Pages

| Page              | URL                          | Notes                              |
|-------------------|------------------------------|------------------------------------|
| **Home**          | `/`                          | Landing page                       |
| **Sign up**       | `/accounts/signup/`          | Self-service registration          |
| **Log in**        | `/accounts/login/`           | Has a "Forgot password?" link      |
| **Profile**       | `/accounts/profile/`         | Edit account + list your tasks     |
| **Tasks**         | `/tasks/Task/`               | Login required, owner-scoped       |
| **Admin**         | `/admin/`                    | Django admin                       |
| **API**           | `/tasks/api/v1/`             | DRF, authentication required       |

---

## Configuration

Settings read from the environment with development fallbacks.

| Variable                  | Default (dev)            | Notes                                  |
|---------------------------|--------------------------|----------------------------------------|
| `DJANGO_SECRET_KEY`       | insecure dev key         | **Required** in production             |
| `DJANGO_DEBUG`            | `True`                   | Set to `False` in production           |
| `DJANGO_ALLOWED_HOSTS`    | empty                    | Comma-separated, e.g. `a.com,b.com`    |
| `DJANGO_EMAIL_BACKEND`    | console                  | Reset emails print to stdout in dev    |
| `DJANGO_EMAIL_HOST`       | `localhost`              | e.g. `smtp.gmail.com`                  |
| `DJANGO_EMAIL_PORT`       | `25`                     | e.g. `587`                             |
| `DJANGO_EMAIL_USE_TLS`    | `False`                  | `True` for most SMTP providers         |
| `DJANGO_EMAIL_HOST_USER`  | empty                    | SMTP username                          |
| `DJANGO_EMAIL_HOST_PASSWORD` | empty                 | SMTP password / app password           |
| `DJANGO_DEFAULT_FROM_EMAIL`  | `taskboard@example.com` | "From" address on outgoing mail        |

> In development the **console email backend** prints reset emails to the
> terminal — no real mail is sent. Configure SMTP for production.

---

## Testing

```bash
pytest                              # all tests
pytest tests/tasks/test_views.py    # one file
pytest -k reset                     # by keyword
```

```bash
python manage.py check              # sanity check
python manage.py check --deploy     # production readiness
```

---

## Project layout

```
TaskBoard/
├── manage.py
├── requirements.txt / requirements-dev.txt
├── TaskBoard/                  # project package
│   ├── settings.py             # env-driven config
│   ├── urls.py                 # root urlconf (web + auth + admin)
│   └── views.py                # signup + profile views
├── tasks/                      # the tasks app
│   ├── models.py · views.py · api.py · serializers.py · forms.py
│   └── templates/tasks/        # task pages
├── templates/                  # base.html + registration/ + index.html
└── tests/tasks/                # pytest test suite
```

---

## Tech stack

**Python 3.12+** · **Django 6** · **Django REST Framework** · **SQLite** (swappable) · **pytest**

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE).
