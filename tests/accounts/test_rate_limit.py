import pytest
from django.core.cache import cache
from django.db import connection
from django.urls import reverse

from tests.conftest import PASSWORD, make_user

ATTEMPT_LIMIT = 5  # allauth : 5 échecs par e-mail et par fenêtre de 5 minutes


def _cache_row_count() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM django_cache")
        return cursor.fetchone()[0]


@pytest.mark.django_db
def test_failed_logins_are_rate_limited_even_with_the_right_password(client):
    make_user("victim@example.com", mfa=False)
    wrong = {"login": "victim@example.com", "password": "wrong-password-123"}
    for _ in range(ATTEMPT_LIMIT):
        client.post(reverse("account_login"), wrong)

    response = client.post(
        reverse("account_login"), {"login": "victim@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert "Trop de tentatives" in response.context["form"].errors["__all__"][0]
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_rate_limit_counters_live_in_the_database_cache(client):
    make_user("victim@example.com")
    client.post(
        reverse("account_login"), {"login": "victim@example.com", "password": "wrong-password-123"}
    )

    assert _cache_row_count() > 0


def test_default_cache_is_shared_across_instances(settings):
    assert settings.CACHES["default"]["BACKEND"].endswith("DatabaseCache")
    assert cache.__class__.__name__ != "LocMemCache"
