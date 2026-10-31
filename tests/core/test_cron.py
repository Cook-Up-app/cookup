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


@pytest.mark.django_db
def test_daily_run_marks_the_database_as_kept_alive(client, settings):
    from apps.core import services

    settings.CRON_SECRET = "s" * 40
    assert services.keepalive_status() == "never"

    response = client.get(
        reverse("core:cron-daily"), headers={"Authorization": f"Bearer {'s' * 40}"}
    )

    assert response.status_code == 200 and response.json()["status"] == "ok"
    assert services.keepalive_status() == "ok"
    assert client.get(reverse("core:health")).json()["keepalive"] == "ok"


@pytest.mark.django_db
def test_keepalive_turns_stale_after_a_missed_day():
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import services

    now = timezone.now()
    services.run_daily_maintenance(now - timedelta(hours=40))

    assert services.keepalive_status(now) == "stale"
    assert services.keepalive_status(now - timedelta(hours=10)) == "ok"


@pytest.mark.django_db
def test_daily_run_purges_expired_unused_invitations_only(owner):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import services
    from apps.households.models import Invitation, Membership

    household = Membership.objects.get(user=owner).household
    now = timezone.now()
    kwargs = {"household": household, "invited_by": owner}
    expired = Invitation.objects.create(
        email="a@x.fr", token_hash="a" * 64, expires_at=now - timedelta(days=1), **kwargs
    )
    used = Invitation.objects.create(
        email="b@x.fr",
        token_hash="b" * 64,
        expires_at=now - timedelta(days=1),
        used_at=now,
        **kwargs,
    )
    open_ = Invitation.objects.create(
        email="c@x.fr", token_hash="c" * 64, expires_at=now + timedelta(days=1), **kwargs
    )
    forever = Invitation.objects.create(
        email="d@x.fr", token_hash="d" * 64, expires_at=None, **kwargs
    )

    report = services.run_daily_maintenance(now)

    remaining = set(Invitation.objects.values_list("pk", flat=True))
    assert report["purged_invitations"] == 1
    assert remaining == {used.pk, open_.pk, forever.pk} and expired.pk not in remaining


@pytest.mark.django_db
def test_daily_run_clears_expired_sessions(client, owner):
    from datetime import timedelta

    from django.contrib.sessions.models import Session
    from django.utils import timezone

    from apps.core import services

    Session.objects.create(
        session_key="old", session_data="x", expire_date=timezone.now() - timedelta(days=1)
    )
    Session.objects.create(
        session_key="new", session_data="x", expire_date=timezone.now() + timedelta(days=1)
    )

    services.run_daily_maintenance()

    assert list(Session.objects.values_list("session_key", flat=True)) == ["new"]
