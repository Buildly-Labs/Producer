from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    """
    Load initial data for the Logic Service.
    This command can be used to populate the database with sample or default data.
    """
    
    help = 'Load initial data for the Logic Service'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-fixtures',
            action='store_true',
            help='Skip loading fixture data',
        )
        parser.add_argument(
            '--skip-episode-types',
            action='store_true',
            help='Skip seeding default episode types',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting to load initial data...')
        )
        
        # Ensure a default admin user exists
        self._ensure_admin_user()
        
        # Seed default episode types
        if not options.get('skip_episode_types'):
            self._seed_episode_types()
        
        if not options['skip_fixtures']:
            # Try to load fixture files if they exist
            try:
                # You can add fixture files in fixtures/ directory
                # call_command('loaddata', 'initial_data.json')
                self.stdout.write('No fixture files to load.')
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Could not load fixtures: {e}')
                )
        
        # You can add custom initial data creation here
        self._create_sample_data()
        
        self.stdout.write(
            self.style.SUCCESS('Successfully loaded initial data!')
        )
    
    def _seed_episode_types(self):
        """Seed default episode types for production_ledger."""
        try:
            from production_ledger.models import EpisodeType
            created = EpisodeType.seed_defaults()
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created {len(created)} default episode types')
                )
            else:
                self.stdout.write('Episode types already exist.')
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'Could not seed episode types: {e}')
            )

    def _create_sample_data(self):
        """Create sample data if needed"""
        # Add logic to create sample data here
        # For example:
        # from logic.models import SomeModel
        # SomeModel.objects.get_or_create(name='Sample', defaults={'description': 'Sample data'})
        
        self.stdout.write('Sample data creation completed.')

    def _ensure_admin_user(self):
        """Create a default admin user if none exists.

        Credentials come from PRODUCER_ADMIN_EMAIL / PRODUCER_ADMIN_PASSWORD
        env-vars and fall back to admin@example.com / changeme123.
        The user is flagged as a superuser so they can access the Django admin.
        """
        import os
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Admin user already exists.')
            return
        email = os.getenv('PRODUCER_ADMIN_EMAIL', 'admin@example.com')
        password = os.getenv('PRODUCER_ADMIN_PASSWORD', 'changeme123')
        User.objects.create_superuser(
            username=email.split('@')[0],
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f'Created default admin user: {email}'))