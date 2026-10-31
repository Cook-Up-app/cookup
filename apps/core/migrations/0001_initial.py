from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    """Table du `DatabaseCache` : compteurs de limitation de débit partagés entre instances."""

    initial = True
    dependencies: list = []
    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
