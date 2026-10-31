from django.db import migrations

from apps.core.reference import Equipment as EquipmentReference


def seed_equipment(apps, schema_editor):
    equipment = apps.get_model("households", "Equipment")
    for code, label in EquipmentReference.choices:
        equipment.objects.update_or_create(code=code, defaults={"label": str(label)})


class Migration(migrations.Migration):
    dependencies = [("households", "0001_initial")]
    operations = [migrations.RunPython(seed_equipment, migrations.RunPython.noop)]
