# Merge migration to resolve conflicting Splice migration branches
# Splice Phase 1.5 added migrations 0005, 0006, 0007, 0008 which conflicted
# with existing migrations. This merge resolves the conflict.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0008_episode_active_segment_constraint'),
        ('production_ledger', '0018_alter_orgapikey_options_and_more'),
    ]

    operations = [
    ]
