"""Logique métier de `core` : maintenance quotidienne et état du maintien de la base."""

from datetime import datetime, timedelta

from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

KEEPALIVE_SOURCE = "database"  # ligne de `sources.SourceState` réservée au maintien de la base
STALE_AFTER = timedelta(hours=36)  # le cron est quotidien : au-delà, il a manqué un passage


def check_database() -> None:
    """Lève `django.db.Error` si la base est injoignable."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def keep_database_alive() -> int:
    """Requête légère qui évite la mise en pause du projet Supabase Free."""
    check_database()
    return Session.objects.count()


def purge_expired_invitations(now: datetime) -> int:
    from apps.households.models import Invitation

    deleted, _ = Invitation.objects.filter(expires_at__lt=now, used_at__isnull=True).delete()
    return deleted


def run_daily_maintenance(now: datetime | None = None) -> dict:
    """Tâche quotidienne : maintien de la base, purge des invitations expirées et des sessions."""
    from apps.sources.models import SourceState

    now = now or timezone.now()
    sessions = keep_database_alive()
    purged = purge_expired_invitations(now)
    call_command("clearsessions", verbosity=0)
    SourceState.objects.update_or_create(source=KEEPALIVE_SOURCE, defaults={"last_request_at": now})
    return {"sessions": sessions, "purged_invitations": purged}


def keepalive_status(now: datetime | None = None) -> str:
    """« ok » si la tâche quotidienne a tourné récemment, « stale » sinon, « never » avant."""
    from apps.sources.models import SourceState

    now = now or timezone.now()
    state = SourceState.objects.filter(source=KEEPALIVE_SOURCE).first()
    if state is None or state.last_request_at is None:
        return "never"
    return "ok" if now - state.last_request_at <= STALE_AFTER else "stale"
