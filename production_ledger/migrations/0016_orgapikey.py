import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0015_platformcomment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # SeparateDatabaseAndState: update Django's internal migration state so it
    # knows the model exists, but run NO SQL. The table and indexes already
    # exist in production from a previous partial run.
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # touch nothing in the DB
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
