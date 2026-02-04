# Generated manually for data-driven EpisodeType

import uuid
from django.db import migrations, models
import django.db.models.deletion


def seed_episode_types_and_migrate(apps, schema_editor):
    """Create episode types and migrate existing episode data."""
    EpisodeType = apps.get_model('production_ledger', 'EpisodeType')
    Episode = apps.get_model('production_ledger', 'Episode')
    
    # Define the default types with their slugs matching old values
    defaults = [
        {
            'name': 'Global',
            'slug': 'global',
            'description': 'Global perspective episodes covering worldwide AI developments',
            'color': '#3B82F6',
            'icon': '🌍',
            'sort_order': 1,
        },
        {
            'name': 'Ops',
            'slug': 'ops',
            'description': 'Operations and implementation focused episodes',
            'color': '#10B981',
            'icon': '⚙️',
            'sort_order': 2,
        },
        {
            'name': 'Ethics',
            'slug': 'ethics',
            'description': 'AI ethics, policy, and responsible AI discussions',
            'color': '#8B5CF6',
            'icon': '⚖️',
            'sort_order': 3,
        },
        {
            'name': 'Interview',
            'slug': 'interview',
            'description': 'Guest interview format episodes',
            'color': '#F59E0B',
            'icon': '🎤',
            'sort_order': 4,
        },
        {
            'name': 'Deep Dive',
            'slug': 'deep-dive',
            'description': 'In-depth technical or topic exploration',
            'color': '#EF4444',
            'icon': '🔬',
            'sort_order': 5,
        },
        {
            'name': 'News Roundup',
            'slug': 'news-roundup',
            'description': 'Weekly or periodic news summary episodes',
            'color': '#06B6D4',
            'icon': '📰',
            'sort_order': 6,
        },
        {
            'name': 'Other',
            'slug': 'other',
            'description': 'Other episode formats',
            'color': '#6B7280',
            'icon': '📋',
            'sort_order': 99,
        },
    ]
    
    # Create episode types
    type_map = {}  # slug -> EpisodeType instance
    for type_data in defaults:
        obj, _ = EpisodeType.objects.get_or_create(
            organization_uuid=None,
            slug=type_data['slug'],
            defaults={
                'id': uuid.uuid4(),
                **type_data
            }
        )
        type_map[type_data['slug']] = obj
    
    # Migrate existing episodes - map old string values to new FK
    for episode in Episode.objects.all():
        old_type = episode.episode_type_old
        if old_type and old_type in type_map:
            episode.episode_type = type_map[old_type]
            episode.save(update_fields=['episode_type'])


def reverse_migration(apps, schema_editor):
    """Reverse: Copy FK back to string field."""
    Episode = apps.get_model('production_ledger', 'Episode')
    for episode in Episode.objects.all():
        if episode.episode_type:
            episode.episode_type_old = episode.episode_type.slug
            episode.save(update_fields=['episode_type_old'])


class Migration(migrations.Migration):

    dependencies = [
        ("production_ledger", "0001_initial"),
    ]

    operations = [
        # Step 1: Create the EpisodeType model
        migrations.CreateModel(
            name="EpisodeType",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("organization_uuid", models.UUIDField(blank=True, db_index=True, help_text="Organization UUID. Null means it's a global/default type.", null=True)),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("color", models.CharField(blank=True, default="#6B7280", help_text="Hex color for UI display, e.g. #3B82F6", max_length=7)),
                ("icon", models.CharField(blank=True, help_text="Emoji or icon identifier", max_length=50)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Episode Type",
                "verbose_name_plural": "Episode Types",
                "ordering": ["sort_order", "name"],
                "unique_together": {("organization_uuid", "slug")},
            },
        ),
        
        # Step 2: Rename existing episode_type to episode_type_old
        migrations.RenameField(
            model_name='episode',
            old_name='episode_type',
            new_name='episode_type_old',
        ),
        
        # Step 3: Add new episode_type FK field (nullable)
        migrations.AddField(
            model_name='episode',
            name='episode_type',
            field=models.ForeignKey(
                blank=True,
                help_text='Type/format of the episode',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='episodes',
                to='production_ledger.episodetype',
            ),
        ),
        
        # Step 4: Seed episode types and migrate data
        migrations.RunPython(seed_episode_types_and_migrate, reverse_migration),
        
        # Step 5: Remove the old episode_type_old field
        migrations.RemoveField(
            model_name='episode',
            name='episode_type_old',
        ),
    ]
