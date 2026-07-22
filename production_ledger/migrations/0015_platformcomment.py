"""
Migration 0015 — PlatformComment model for podcast/video comment management.
"""
import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('production_ledger', '0014_youtube_config'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformComment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('organization_uuid', models.UUIDField(db_index=True)),
                ('platform', models.CharField(
                    choices=[
                        ('youtube',      'YouTube'),
                        ('apple',        'Apple Podcasts'),
                        ('spotify',      'Spotify'),
                        ('amazon',       'Amazon Music'),
                        ('iheart',       'iHeartRadio'),
                        ('pocket_casts', 'Pocket Casts'),
                        ('overcast',     'Overcast'),
                        ('castbox',      'Castbox'),
                        ('website',      'Website'),
                        ('email',        'Email / DM'),
                        ('other',        'Other'),
                    ],
                    db_index=True, max_length=50,
                )),
                ('external_id',      models.CharField(blank=True, db_index=True, max_length=255)),
                ('author_name',          models.CharField(blank=True, max_length=255)),
                ('author_channel_url',   models.URLField(blank=True, max_length=500)),
                ('author_profile_image', models.URLField(blank=True, max_length=500)),
                ('body',       models.TextField()),
                ('like_count', models.PositiveIntegerField(default=0)),
                ('platform_created_at', models.DateTimeField(blank=True, null=True)),
                ('synced_at',  models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(
                    choices=[
                        ('new',      'New'),
                        ('read',     'Read'),
                        ('replied',  'Replied'),
                        ('spam',     'Spam'),
                        ('archived', 'Archived'),
                    ],
                    db_index=True, default='new', max_length=20,
                )),
                ('our_reply_text',        models.TextField(blank=True)),
                ('our_reply_sent_at',     models.DateTimeField(blank=True, null=True)),
                ('our_reply_external_id', models.CharField(blank=True, max_length=255)),
                ('show', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='platform_comments',
                    to='production_ledger.show',
                )),
                ('episode', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='platform_comments',
                    to='production_ledger.episode',
                )),
                ('parent', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='replies',
                    to='production_ledger.platformcomment',
                )),
                ('added_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='added_platform_comments',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('replied_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='replied_platform_comments',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-platform_created_at', '-created_at'],
                'indexes': [
                    models.Index(fields=['platform', 'external_id'], name='pl_comment_platform_extid'),
                    models.Index(fields=['organization_uuid', 'status'], name='pl_comment_org_status'),
                    models.Index(fields=['episode', 'platform'], name='pl_comment_ep_platform'),
                ],
            },
        ),
    ]
