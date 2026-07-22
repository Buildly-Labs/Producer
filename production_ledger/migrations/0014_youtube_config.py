"""
Migration 0014 — Add YouTube OAuth integration fields to PodcastFeedConfig.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0013_videoshort_platform_captions'),
    ]

    operations = [
        migrations.AddField(
            model_name='podcastfeedconfig',
            name='youtube_client_id',
            field=models.CharField(blank=True, help_text='Google OAuth client ID', max_length=255),
        ),
        migrations.AddField(
            model_name='podcastfeedconfig',
            name='youtube_client_secret',
            field=models.CharField(blank=True, help_text='Google OAuth client secret', max_length=255),
        ),
        migrations.AddField(
            model_name='podcastfeedconfig',
            name='youtube_refresh_token',
            field=models.TextField(blank=True, help_text='Stored OAuth refresh token after connecting YouTube'),
        ),
        migrations.AddField(
            model_name='podcastfeedconfig',
            name='youtube_channel_id',
            field=models.CharField(blank=True, help_text='YouTube channel ID (auto-populated on connect)', max_length=100),
        ),
        migrations.AddField(
            model_name='podcastfeedconfig',
            name='youtube_channel_name',
            field=models.CharField(blank=True, help_text='YouTube channel display name', max_length=255),
        ),
        migrations.AddField(
            model_name='podcastfeedconfig',
            name='youtube_default_privacy',
            field=models.CharField(
                choices=[('public', 'Public'), ('unlisted', 'Unlisted'), ('private', 'Private')],
                default='public',
                max_length=20,
            ),
        ),
    ]
