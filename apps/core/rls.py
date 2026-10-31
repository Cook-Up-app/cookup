"""Row Level Security sans politique sur toutes les tables du schéma `public`.

Défense en profondeur : même si la Data API de Supabase était exposée par erreur, les rôles
`anon` et `authenticated` ne verraient aucune ligne. Django se connecte avec le propriétaire des
tables, qui n'est pas soumis à RLS (pas de `FORCE`).
"""

from django.db import connections

LIST_TABLES_SQL = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
ENABLE_RLS_SQL = 'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'


def enable_rls_on_all_tables(using: str = "default") -> list[str]:
    """Idempotent ; retourne les tables traitées. Sans effet hors PostgreSQL."""
    conn = connections[using]
    if conn.vendor != "postgresql":
        return []
    with conn.cursor() as cursor:
        cursor.execute(LIST_TABLES_SQL)
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(ENABLE_RLS_SQL.format(table=table.replace('"', '""')))
    return tables
