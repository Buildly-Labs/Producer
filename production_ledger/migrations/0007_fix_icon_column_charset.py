from django.db import migrations


def _fix_icon_charset(apps, schema_editor):
    """ALTER icon column charset — MySQL only, no-op on all other backends."""
    if schema_editor.connection.vendor != 'mysql':
        return
    schema_editor.execute(
        """
        ALTER TABLE `production_ledger_episodetype`
            MODIFY COLUMN `icon` VARCHAR(50)
                CHARACTER SET utf8mb4
                COLLATE utf8mb4_unicode_ci
                NOT NULL DEFAULT ''
        """
    )


def _reverse_fix_icon_charset(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    schema_editor.execute(
        """
        ALTER TABLE `production_ledger_episodetype`
            MODIFY COLUMN `icon` VARCHAR(50)
                CHARACTER SET utf8
                COLLATE utf8_unicode_ci
                NOT NULL DEFAULT ''
        """
    )


class Migration(migrations.Migration):
    """
    ALTER the `icon` column on production_ledger_episodetype to use utf8mb4
    so that 4-byte emoji characters (e.g. 🌍 U+1F30D) can be stored.

    MySQL only — RunPython guard makes this a no-op on PostgreSQL and SQLite.
    """

    dependencies = [
        ("production_ledger", "0006_auto_20260416_2221"),
    ]

    operations = [
        migrations.RunPython(_fix_icon_charset, _reverse_fix_icon_charset),
    ]
