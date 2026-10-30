"""Logique métier de `core` : vérifications d'état de la base."""

from django.contrib.sessions.models import Session
from django.db import connection


def check_database() -> None:
    """Lève `django.db.Error` si la base est injoignable."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def keep_database_alive() -> int:
    """Requête légère qui évite la mise en pause du projet Supabase Free."""
    check_database()
    return Session.objects.count()
