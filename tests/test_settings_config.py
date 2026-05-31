"""Guard the DATABASE_URL wiring (pure config — no DB connection)."""

import dj_database_url


def tests_database_url_parses_postgres():
    config = dj_database_url.parse(
        "postgres://user:pass@db:5432/taskboard"
    )
    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "taskboard"
    assert config["HOST"] == "db"
    assert config["PORT"] == 5432


def tests_database_url_defaults_to_sqlite():
    # With no DATABASE_URL, config() uses the SQLite default the settings pass.
    config = dj_database_url.config(
        env="DATABASE_URL_DEFINITELY_UNSET", default="sqlite:///db.sqlite3"
    )
    assert config["ENGINE"] == "django.db.backends.sqlite3"
