from django.db import migrations


class Migration(migrations.Migration):
    """
    ALTER the `icon` column on production_ledger_episodetype to use utf8mb4
    so that 4-byte emoji characters (e.g. 🌍 U+1F30D) can be stored.

    MySQL's default `utf8` charset only supports 3-byte code points; emoji
    require the `utf8mb4` charset.  This migration is a no-op on SQLite and
    PostgreSQL (RunSQL returns gracefully when the dialect doesn't use
    CHARACTER SET).
    """

    dependencies = [
        ("production_ledger", "0006_auto_20260416_2221"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE `production_ledger_episodetype`
                    MODIFY COLUMN `icon` VARCHAR(50)
                        CHARACTER SET utf8mb4
                        COLLATE utf8mb4_unicode_ci
                        NOT NULL DEFAULT '';
            """,
            # Reverse: revert to the server-default charset (utf8).
            # In practice you would rarely need to run this, but it keeps the
            # migration reversible.
            reverse_sql="""
                ALTER TABLE `production_ledger_episodetype`
                    MODIFY COLUMN `icon` VARCHAR(50)
                        CHARACTER SET utf8
                        COLLATE utf8_unicode_ci
                        NOT NULL DEFAULT '';
            """,
            hints={"target_db": "mysql"},
        ),
    ]
