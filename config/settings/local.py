"""Développement local : PostgreSQL du `docker-compose.yml`, aucun secret de production."""

from apps.core.env import env_str

from .base import *  # noqa: F403
from .base import database_config, database_url

DEBUG = True
SECRET_KEY = "dev-only-insecure-key"  # noqa: S105
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

DATABASES = {
    "default": database_config(database_url("postgres://cookup:cookup@localhost:5433/cookup"))
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

ADMIN_PATH = env_str("ADMIN_PATH", "admin/")
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = True  # passkeys sur http://localhost, développement seulement
