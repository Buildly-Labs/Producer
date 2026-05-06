# Repair migration: ensures `label` and `platform` columns exist on
# production_ledger_mediaasset.  Migration 0004 may have been faked on some
# production instances (to repair Django migration history), which left these
# columns absent from the actual database schema.  This migration is purely
# a database-state repair; Django ORM state is already correct from 0004.

from django.db import migrations, connection

TABLE = "production_ledger_mediaasset"


def _column_exists(column):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, TABLE)
    return any(col.name == column for col in description)


def _add_if_missing(apps, schema_editor):
    vendor = schema_editor.connection.vendor

    if not _column_exists("label"):
        if vendor == "mysql":
            schema_editor.execute(
                "ALTER TABLE `%s` ADD COLUMN `label` VARCHAR(200) NOT NULL DEFAULT ''" % TABLE
            )
        else:
            schema_editor.execute(
                'ALTER TABLE "%s" ADD COLUMN "label" VARCHAR(200) NOT NULL DEFAULT \'\'' % TABLE
            )

    if not _column_exists("platform"):
        if vendor == "mysql":
            schema_editor.execute(
                "ALTER TABLE `%s` ADD COLUMN `platform` VARCHAR(30) NOT NULL DEFAULT ''" % TABLE
            )
        else:
            schema_editor.execute(
                'ALTER TABLE "%s" ADD COLUMN "platform" VARCHAR(30) NOT NULL DEFAULT \'\'' % TABLE
            )


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("production_ledger", "0011_alter_aiartifact_artifact_type"),
    ]

    operations = [
        # state_operations is empty — Django ORM state already reflects these
        # fields from migration 0004.  Only the physical columns may be absent.
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(_add_if_missing, reverse_code=_noop),
            ],
        ),
    ]
