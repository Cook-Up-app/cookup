import importlib

import pytest
from django.test import override_settings


@pytest.fixture
def production_settings(monkeypatch):
    """Applique les réglages de production (hors base de données) pendant un test."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-production-use-0123456789")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost:5433/cookup")
    module = importlib.import_module("config.settings.production")
    module = importlib.reload(module)
    values = {
        name: getattr(module, name)
        for name in dir(module)
        if name.isupper() and name not in {"DATABASES", "SECRET_KEY", "ALLOWED_HOSTS"}
    }
    with override_settings(ALLOWED_HOSTS=["testserver"], **values):
        yield module
