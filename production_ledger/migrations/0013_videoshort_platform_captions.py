"""
Add platform_captions JSONField to VideoShort for per-platform caption storage.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0012_repair_media_columns'),
    ]

    operations = [
        migrations.AddField(
            model_name='videoshort',
            name='platform_captions',
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text='Per-platform captions: {"tiktok": "...", "youtube_shorts": "...", "instagram": "...", "linkedin": "..."}',
            ),
        ),
    ]
