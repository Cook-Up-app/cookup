import pytest
from django.db import connection


@pytest.mark.django_db
def test_every_public_table_has_row_level_security():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity"
        )
        unprotected = [row[0] for row in cursor.fetchall()]

    assert unprotected == []


@pytest.mark.django_db
def test_application_tables_have_no_policy():
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")

        assert cursor.fetchone()[0] == 0
