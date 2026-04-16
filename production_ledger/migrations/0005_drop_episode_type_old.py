# Cleanup: drop episode_type_old column left behind when migration 0002 was faked

from django.db import migrations


def drop_episode_type_old(apps, schema_editor):
    """Drop episode_type_old column if it still exists in the database."""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'production_ledger_episode' "
            "AND column_name = 'episode_type_old'"
        )
        if cursor.fetchone()[0] > 0:
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
