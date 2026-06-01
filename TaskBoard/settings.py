
"""
Django settings for TaskBoard project.

A simple task board built with Django Builder

For more information on this file, see
https://docs.djangoproject.com/

"""

import os
from pathlib import Path

import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

# Keep the real key in the environment in production. The fallback is dev-only.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-only-^l)7d*%h&db4uft@dk%h-w&nup#pu%)a!d)c7jwgoixo5_hm0$',
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if os.environ.get('DJANGO_ALLOWED_HOSTS') else []

# Comma-separated, e.g. "https://app.example.com" — required for HTTPS POSTs
# once served behind a real domain.
CSRF_TRUSTED_ORIGINS = (
    os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS')
    else []
)

# Application definition
INSTALLED_APPS = [
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'drf_spectacular',

    'organizations',
    'tasks',
]


# Django REST Framework
# https://www.django-rest-framework.org/

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.OrderingFilter',
        'rest_framework.filters.SearchFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'TaskBoard API',
    'DESCRIPTION': 'Org/project-scoped task management API.',
    'VERSION': 'v1',
    'SERVE_INCLUDE_SCHEMA': False,
}


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'TaskBoard.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'organizations.context_processors.organizations',
            ],
        },
    },
]

WSGI_APPLICATION = 'TaskBoard.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

# Configured from DATABASE_URL when set (e.g. postgres://… in production / the
# docker-compose stack); falls back to the SQLite dev database otherwise.
DATABASES = {
    'default': dj_database_url.config(
        env='DATABASE_URL',
        default='sqlite:///' + str(BASE_DIR / 'db.sqlite3'),
        conn_max_age=600,
    )
}


# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/
# Collected to STATIC_ROOT by `collectstatic` and served by WhiteNoise.

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        # WhiteNoise's hashed-manifest storage in production; plain storage in
        # dev/tests so {% static %} resolves without running collectstatic first.
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
            if not DEBUG
            else 'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Production security. Enabled when DEBUG is off; each is overridable by env so a
# non-TLS deployment can opt out. These also satisfy `manage.py check --deploy`.

def _env_bool(name, default):
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes', 'on')


if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = _env_bool('DJANGO_SESSION_COOKIE_SECURE', True)
    CSRF_COOKIE_SECURE = _env_bool('DJANGO_CSRF_COOKIE_SECURE', True)
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
        'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', True
    )
    SECURE_HSTS_PRELOAD = _env_bool('DJANGO_SECURE_HSTS_PRELOAD', True)
    # Trust the X-Forwarded-Proto header from a TLS-terminating proxy.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Authentication
# https://docs.djangoproject.com/en/6.0/topics/auth/default/

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'tasks:Task_list'
LOGOUT_REDIRECT_URL = 'index'


# Email
# Used by the password-reset flow. In development the console backend prints
# messages to stdout; set DJANGO_EMAIL_BACKEND (and SMTP vars) in production.

EMAIL_BACKEND = os.environ.get(
    'DJANGO_EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('DJANGO_EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('DJANGO_EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.environ.get('DJANGO_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('DJANGO_EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('DJANGO_EMAIL_USE_TLS', 'False') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get(
    'DJANGO_DEFAULT_FROM_EMAIL', 'taskboard@example.com'
)
