# Cleanup: drop episode_type_old column left behind when migration 0002 was faked

from django.db import migrations


def _column_exists(schema_editor, table_name, column_name):
    with schema_editor.connection.cursor() as cursor:
        description = schema_editor.connection.introspection.get_table_description(cursor, table_name)
    return any(col.name == column_name for col in description)


def drop_episode_type_old(apps, schema_editor):
    """Drop episode_type_old column if it still exists in the database."""
    table_name = "production_ledger_episode"
    if _column_exists(schema_editor, table_name, "episode_type_old"):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE production_ledger_episode DROP COLUMN episode_type_old"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("production_ledger", "0004_add_media_platform_and_label"),
    ]

    operations = [
        migrations.RunPython(drop_episode_type_old, migrations.RunPython.noop),
    ]
