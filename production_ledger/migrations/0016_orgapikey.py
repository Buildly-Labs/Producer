import uuid
import django.db.models.deletion
from django.apps import apps as global_apps
from django.conf import settings
from django.db import migrations, models


def _table_exists(schema_editor, table_name):
    return table_name in schema_editor.connection.introspection.table_names()


def create_orgapikey_if_missing(apps, schema_editor):
    """
    On a database where this table already exists (production, from a prior
    partial run when this migration was first written), do nothing. On a
    fresh database (local dev, CI, a new install), create it for real -
    otherwise the model exists only in Django's migration state and every
    later migration touching OrgAPIKey fails with "no such table".

    The state_operations below add OrgAPIKey to migration state, but this
    database_operations code runs against the PRE-state apps registry
    (matching how SeparateDatabaseAndState orders the two), so the model
    isn't there yet - fall back to the live app registry, same as 0009.
    """
    try:
        OrgAPIKey = apps.get_model('production_ledger', 'OrgAPIKey')
    except LookupError:
        OrgAPIKey = global_apps.get_model('production_ledger', 'OrgAPIKey')
    if not _table_exists(schema_editor, 'production_ledger_orgapikey'):
        schema_editor.create_model(OrgAPIKey)


def reverse_create_orgapikey(apps, schema_editor):
    # Keep reverse migration non-destructive for safety in shared environments.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0015_platformcomment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # SeparateDatabaseAndState: state always reflects that OrgAPIKey exists;
    # the database side only creates it when the table isn't already there
    # (see create_orgapikey_if_missing).
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(create_orgapikey_if_missing, reverse_create_orgapikey),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='OrgAPIKey',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('organization_uuid', models.UUIDField(db_index=True)),
                        ('service', models.CharField(
                            max_length=50,
                            choices=[('openai', 'OpenAI')],
                        )),
                        ('api_key', models.CharField(max_length=512)),
                        ('label', models.CharField(blank=True, default='', max_length=100)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('updated_by', models.ForeignKey(
                            blank=True,
                            null=True,
                            on_delete=django.db.models.deletion.SET_NULL,
                            related_name='+',
                            to=settings.AUTH_USER_MODEL,
                        )),
                    ],
                    options={
                        'db_table': 'production_ledger_orgapikey',
                        'unique_together': {('organization_uuid', 'service')},
                    },
                ),
            ],
        ),
    ]
