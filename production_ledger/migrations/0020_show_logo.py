# Generated migration to add missing logo field to Show model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("production_ledger", "0019_merge_splice_migrations"),
    ]

    operations = [
        migrations.AddField(
            model_name="show",
            name="logo",
            field=models.ImageField(
                blank=True,
                help_text="Show logo for the second-screen display and other branding",
                null=True,
                upload_to="shows/<uuid:organization_uuid>/<uuid:pk>/branding/",
            ),
        ),
    ]
