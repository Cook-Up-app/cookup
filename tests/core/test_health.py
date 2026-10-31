import pytest
from django.db import OperationalError
from django.urls import reverse


@pytest.mark.django_db
def test_health_ok(client):
    response = client.get(reverse("core:health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up", "keepalive": "never"}


def test_health_degraded_when_database_down(client, monkeypatch):
    def fail() -> None:
        raise OperationalError("connexion refusée")

    monkeypatch.setattr("apps.core.services.check_database", fail)

    response = client.get(reverse("core:health"))

    assert response.status_code == 503
    assert "connexion" not in response.content.decode()


def test_health_rejects_post(client):
    assert client.post(reverse("core:health")).status_code == 405


@pytest.mark.django_db
def test_health_accepts_head(client):
    assert client.head(reverse("core:health")).status_code == 200
