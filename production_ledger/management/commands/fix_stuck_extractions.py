"""
Management command to mark stuck audio extraction assets as failed.

Usage:
    python manage.py fix_stuck_extractions            # dry run
    python manage.py fix_stuck_extractions --apply    # apply fixes
    python manage.py fix_stuck_extractions --apply --minutes 120  # only assets older than 2h
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Mark stuck PENDING/PROCESSING audio-extraction assets as FAILED'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually update the records (default is dry-run)',
        )
        parser.add_argument(
            '--minutes', type=int, default=30,
            help='Only fix assets stuck for longer than this many minutes (default 30)',
        )

    def handle(self, *args, **options):
        from production_ledger.models import MediaAsset
        from production_ledger.constants import IngestionStatus

        apply = options['apply']
        cutoff = timezone.now() - datetime.timedelta(minutes=options['minutes'])

        stuck = MediaAsset.objects.filter(
            ingestion_status__in=[IngestionStatus.PENDING, IngestionStatus.PROCESSING],
            created_at__lt=cutoff,
            # Only extraction-style assets (no external_url yet means never finished)
            asset_type='audio',
        ).order_by('-created_at')

        if not stuck.exists():
            self.stdout.write(self.style.SUCCESS('No stuck extraction assets found.'))
            return

        self.stdout.write(f'Found {stuck.count()} stuck asset(s) (older than {options["minutes"]} min):')
        for asset in stuck:
            age = timezone.now() - asset.created_at
            self.stdout.write(
                f'  [{asset.pk}] "{asset.label}" | '
                f'status={asset.ingestion_status} | '
                f'age={int(age.total_seconds() // 60)}min | '
                f'episode={asset.episode_id}'
            )

        if not apply:
            self.stdout.write(self.style.WARNING('\nDry run — pass --apply to update records.'))
            return

        updated = stuck.update(
            ingestion_status=IngestionStatus.FAILED,
            error_message='Extraction timed out or crashed without recording an error. '
                          'Please retry the audio extraction.',
        )
        self.stdout.write(self.style.SUCCESS(f'Marked {updated} asset(s) as FAILED.'))
