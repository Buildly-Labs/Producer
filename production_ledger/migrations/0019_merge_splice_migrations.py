# Merge migration to resolve conflicting Splice migration branches.
# Removed conflicting duplicate migrations 0005-0008 from Splice Phase 1.5
# which conflicted with main branch migrations. The main branch timeline is:
# 0001-0004, 0005_drop_episode_type_old, 0006_auto_*, 0007_fix_icon_column_charset,
# 0008_add_segment_live_recording_fields, 0009-0018, then this merge.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('production_ledger', '0018_alter_orgapikey_options_and_more'),
    ]

    operations = [
    ]
