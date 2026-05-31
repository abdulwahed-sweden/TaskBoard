#!/usr/bin/env bash
# Apply migrations and collect static files, then run the given command
# (gunicorn by default). Keeps the image's runtime startup self-contained.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
