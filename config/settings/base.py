"""Réglages communs à tous les environnements."""

from pathlib import Path

import dj_database_url
from django.utils.csp import CSP

from apps.core.env import env_bool, env_int, env_list, env_required, env_str

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY_FALLBACKS = env_list("SECRET_KEY_FALLBACKS")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
CRON_SECRET = env_str("CRON_SECRET")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.contrib.postgres",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "apps.core",
    "apps.accounts",
    "apps.households",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.PermissionsPolicyMiddleware",
    # En dernier : ses redirections traversent ainsi CSP et en-têtes de sécurité.
    "apps.accounts.middleware.AccessPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
            ],
        },
    },
]


def database_url(default: str | None = None) -> str:
    """URL de la base ; `USE_DIRECT_DATABASE=1` choisit la connexion directe (migrations)."""
    if env_bool("USE_DIRECT_DATABASE"):
        return env_required("DATABASE_DIRECT_URL")
    if default is None:
        return env_required("DATABASE_URL")
    return env_str("DATABASE_URL", default)


def database_config(url: str) -> dict:
    """Configuration compatible avec le pooler transactionnel de Supabase (port 6543)."""
    config = dj_database_url.parse(url, conn_max_age=0)
    config["DISABLE_SERVER_SIDE_CURSORS"] = True
    # Le mode transactionnel ne supporte pas les instructions préparées.
    config.setdefault("OPTIONS", {})["prepare_threshold"] = None
    return config


PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
PASSWORD_RESET_TIMEOUT = 24 * 60 * 60
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"

# Inscription fermée (adaptateur), pas d'e-mail : les liens d'invitation et de
# réinitialisation sont générés par le propriétaire du foyer.
ACCOUNT_ADAPTER = "apps.accounts.adapters.ClosedAccountAdapter"
ACCOUNT_USER_MODEL_USERNAME_FIELD = None  # le modèle utilisateur n'a pas de `username`
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_REAUTHENTICATION_REQUIRED = True
ACCOUNT_REAUTHENTICATION_TIMEOUT = 5 * 60
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"
MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_TOTP_ISSUER = "Menu du jour"

# Les compteurs de limitation de débit doivent être partagés entre instances serverless.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Chemin de l'administration ; désactivée si la variable est absente (cas de la production).
ADMIN_PATH = env_str("ADMIN_PATH")

LANGUAGE_CODE = "fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
# Pas de révocation d'accès liée au temps : session d'un an, prolongée à chaque requête.
SESSION_COOKIE_AGE = 365 * 24 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True  # durée glissante
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Sans `unsafe-inline` ni `unsafe-eval` : Alpine.js utilisera sa variante CSP.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# 0 = les invitations n'expirent pas (usage unique et révocation manuelle restent en vigueur).
INVITATION_TTL_DAYS = env_int("INVITATION_TTL_DAYS", 0)
