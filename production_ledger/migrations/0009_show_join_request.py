from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0008_add_segment_live_recording_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShowJoinRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('desired_role', models.CharField(choices=[('admin', 'Admin'), ('host', 'Host'), ('producer', 'Producer'), ('editor', 'Editor'), ('guest', 'Guest')], default='guest', max_length=20)),
                ('message', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('declined', 'Declined')], default='pending', max_length=20)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_show_join_requests', to=settings.AUTH_USER_MODEL)),
                ('show', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='join_requests', to='production_ledger.show')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='show_join_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Show Join Request',
                'verbose_name_plural': 'Show Join Requests',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='showjoinrequest',
            index=models.Index(fields=['show', 'status'], name='production__show_id_status_idx'),
        ),
        migrations.AddIndex(
            model_name='showjoinrequest',
            index=models.Index(fields=['user', 'status'], name='production__user_id_status_idx'),
        ),
    ]
