# Migration 0018: Field and index alterations
# This migration was generated in production where tables already exist.
# For fresh databases, use SeparateDatabaseAndState to only update Django's state.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("production_ledger", "0017_background_task"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # In production, all these tables exist and need alterations.
        # In fresh databases, they don't exist yet, so skip DB operations.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Skipped: RenameIndex operations (indexes don't exist in fresh DBs)
                # Skipped: All AlterField operations (tables created later with current schema)
                # Skipped: AddIndex operation (covered by 0016 unique_together constraint)
                # Skipped: AlterModelTable (not needed in fresh DBs)
            ],
            state_operations=[
                # Update Django's model state to match production schema
                migrations.AlterModelOptions(
                    name="orgapikey",
                    options={
                        "verbose_name": "Organization API Key",
                        "verbose_name_plural": "Organization API Keys",
                    },
                ),
                migrations.AlterField(
                    model_name="backgroundtask",
                    name="organization_uuid",
                    field=models.UUIDField(db_index=True),
                ),
                migrations.AlterField(
                    model_name="orgapikey",
                    name="api_key",
                    field=models.CharField(
                        help_text="API key for this service", max_length=512
                    ),
                ),
                migrations.AlterField(
                    model_name="orgapikey",
                    name="label",
                    field=models.CharField(
                        blank=True,
                        help_text="Optional label, e.g. 'Production key'",
                        max_length=100,
                    ),
                ),
                migrations.AlterField(
                    model_name="orgapikey",
                    name="service",
                    field=models.CharField(
                        choices=[("openai", "OpenAI (TTS, AI writing)")], max_length=50
                    ),
                ),
                migrations.AlterField(
                    model_name="orgapikey",
                    name="updated_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="podcastdistribution",
                    name="created_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="podcastdistribution",
                    name="platform",
                    field=models.CharField(
                        choices=[
                            ("apple", "Apple Podcasts"),
                            ("spotify", "Spotify"),
                            ("amazon", "Amazon Music"),
                            ("google", "YouTube Music / Google Podcasts"),
                            ("iheart", "iHeartRadio"),
                            ("stitcher", "Stitcher (Discontinued)"),
                            ("pocket_casts", "Pocket Casts"),
                            ("overcast", "Overcast"),
                            ("castbox", "Castbox"),
                            ("rss", "RSS Feed"),
                        ],
                        max_length=30,
                    ),
                ),
                migrations.AlterField(
                    model_name="podcastdistribution",
                    name="updated_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="podcastfeedconfig",
                    name="created_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="podcastfeedconfig",
                    name="updated_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="videoshort",
                    name="created_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="videoshort",
                    name="updated_by",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
