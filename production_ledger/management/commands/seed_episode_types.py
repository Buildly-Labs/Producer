"""
Management command to seed default episode types.

Usage:
    python manage.py seed_episode_types
    python manage.py seed_episode_types --org <organization_uuid>
"""
from django.core.management.base import BaseCommand

from production_ledger.models import EpisodeType


class Command(BaseCommand):
    help = 'Seed default episode types into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization UUID to create types for (leave empty for global defaults)',
        )

    def handle(self, *args, **options):
        org_uuid = options.get('org')
        
        if org_uuid:
            self.stdout.write(f'Seeding episode types for organization: {org_uuid}')
        else:
            self.stdout.write('Seeding global default episode types...')
        
        created_types = EpisodeType.seed_defaults(organization_uuid=org_uuid)
        
        if created_types:
            self.stdout.write(self.style.SUCCESS(
                f'Created {len(created_types)} episode types:'
            ))
            for et in created_types:
                self.stdout.write(f'  - {et.icon} {et.name} ({et.slug})')
        else:
            self.stdout.write(self.style.WARNING(
                'No new episode types created (they may already exist)'
            ))
        
        # Show total count
        if org_uuid:
            total = EpisodeType.objects.filter(organization_uuid=org_uuid).count()
        else:
            total = EpisodeType.objects.filter(organization_uuid__isnull=True).count()
        
        self.stdout.write(f'\nTotal episode types: {total}')
