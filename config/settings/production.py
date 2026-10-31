"""Production Vercel : TLS terminé par le proxy, cookies et en-têtes durcis."""

from apps.core.env import env_required

from .base import *  # noqa: F403
from .base import database_config, database_url

DEBUG = False
SECRET_KEY = env_required("SECRET_KEY")
DATABASES = {"default": database_config(database_url())}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Vercel exécute collectstatic au build et sert /static depuis son CDN : la fonction n'a pas
    # de dossier staticfiles, donc pas de stockage à manifeste (il lèverait une erreur 500).
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 365 * 24 * 60 * 60
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Le préfixe `__Host-` impose Secure, Path=/ et l'absence de Domain.
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-sessionid"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_NAME = "__Host-csrftoken"
