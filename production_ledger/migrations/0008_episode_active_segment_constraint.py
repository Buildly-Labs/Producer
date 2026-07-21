# Generated migration for Episode.active_segment validation
# The clean() method in the Episode model validates that active_segment
# belongs to the same episode, preventing cross-episode assignment.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0007_episode_overlay_token'),
    ]

    operations = [
        # Note: Database-level check constraints with joined fields are not
        # supported in SQLite. Instead, validation is enforced at the ORM level
        # via Episode.clean() which is called during model.save().
    ]
