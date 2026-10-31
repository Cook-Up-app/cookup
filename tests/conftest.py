import importlib

import pytest
from allauth.mfa.models import Authenticator
from django.test import override_settings

from apps.accounts.models import User
from apps.households import services

PASSWORD = "correct-horse-battery-staple"


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


def make_user(email: str, *, mfa: bool = True, name: str = "") -> User:
    user = User.objects.create_user(email, PASSWORD, display_name=name or email.split("@")[0])
    if mfa:
        Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return user


@pytest.fixture
def owner(db):
    user = make_user("owner@example.com")
    services.create_household(user, "Foyer A")
    return user


@pytest.fixture
def other_owner(db):
    user = make_user("other@example.com")
    services.create_household(user, "Foyer B")
    return user


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def recent_reauth(monkeypatch):
    """Simule une réauthentification récente (allauth la lit dans la session)."""
    monkeypatch.setattr(
        "allauth.account.internal.flows.reauthentication.did_recently_reauthenticate",
        lambda request: True,
    )


def seed_catalog() -> None:
    """Ingrédients et recettes de départ, sans la renormalisation (inutile sur une base vide)."""
    from apps.catalog.seeding import seed_ingredients
    from apps.catalog.starter import load_starter_recipes

    seed_ingredients()
    load_starter_recipes()
