import pytest
from django.urls import reverse

HTTPS = {"secure": True}


@pytest.fixture
def response(client, production_settings):
    return client.get(reverse("core:home"), **HTTPS)


def test_hsts_one_year_with_subdomains(response):
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_csp_is_strict(response):
    policy = response.headers["Content-Security-Policy"]

    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy
    assert "frame-ancestors 'none'" in policy
    assert "default-src 'self'" in policy


def test_browser_hardening_headers(response):
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_http_is_redirected_to_https(client, production_settings):
    response = client.get(reverse("core:home"))

    assert response.status_code == 301
    assert response["Location"].startswith("https://")


def test_cookie_settings(production_settings):
    assert production_settings.SESSION_COOKIE_SECURE is True
    assert production_settings.SESSION_COOKIE_NAME.startswith("__Host-")
    assert production_settings.CSRF_COOKIE_SECURE is True
    assert production_settings.CSRF_COOKIE_NAME.startswith("__Host-")
    assert production_settings.SESSION_COOKIE_HTTPONLY is True
    assert production_settings.SESSION_COOKIE_SAMESITE == "Lax"


def test_production_requires_secret_key(monkeypatch):
    import importlib

    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost/db")
    module = importlib.import_module("config.settings.production")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        importlib.reload(module)


def test_transaction_pooler_compatible_database_config(production_settings):
    from config.settings.base import database_config

    config = database_config("postgres://u:p@pooler.example:6543/postgres?sslmode=require")

    assert config["DISABLE_SERVER_SIDE_CURSORS"] is True
    assert config["CONN_MAX_AGE"] == 0
    assert config["OPTIONS"]["prepare_threshold"] is None
    assert config["OPTIONS"]["sslmode"] == "require"


def test_wsgi_entrypoint_forces_production_settings(monkeypatch):
    import importlib

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.local")
    monkeypatch.setattr("django.core.wsgi.get_wsgi_application", lambda: object())
    import config.wsgi

    importlib.reload(config.wsgi)

    import os

    assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings.production"
