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

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting to load initial data...')
        )
        
        # Add any initial data loading logic here
        # For example, creating default groups, permissions, etc.
        
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

    def _create_sample_data(self):
        """Create sample data if needed"""
        # Add logic to create sample data here
        # For example:
        # from logic.models import SomeModel
        # SomeModel.objects.get_or_create(name='Sample', defaults={'description': 'Sample data'})
        
        self.stdout.write('Sample data creation completed.')