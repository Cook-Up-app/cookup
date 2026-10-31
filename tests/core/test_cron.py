import pytest
from django.test import override_settings
from django.urls import reverse

SECRET = "x" * 40


@pytest.fixture
def url():
    return reverse("core:cron-daily")


@override_settings(CRON_SECRET=SECRET)
@pytest.mark.django_db
def test_cron_accepts_valid_bearer(client, url):
    response = client.get(url, headers={"Authorization": f"Bearer {SECRET}"})

    assert response.status_code == 200


@override_settings(CRON_SECRET=SECRET)
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": SECRET}],
)
def test_cron_rejects_missing_or_wrong_token(client, url, headers):
    assert client.get(url, headers=headers).status_code == 401


@override_settings(CRON_SECRET="")
def test_cron_refused_when_secret_unset(client, url):
    response = client.get(url, headers={"Authorization": "Bearer "})

    assert response.status_code == 401
