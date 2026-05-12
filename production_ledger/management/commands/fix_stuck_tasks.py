"""
Startup cleanup: mark orphaned background tasks and extraction assets as failed.

Designed to run automatically at container start (before gunicorn) so that
tasks whose worker threads died with a previous container don't show as
"in progress" forever in the UI.

Usage:
    python manage.py fix_stuck_tasks              # auto mode (≥5 min threshold)
    python manage.py fix_stuck_tasks --minutes 30 # only fix tasks older than 30m
"""
import datetime
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_MINUTES = 5  # tasks stuck longer than this are considered orphaned


class Command(BaseCommand):
    help = 'Mark orphaned PENDING/PROCESSING/RUNNING tasks as FAILED/TIMEOUT at startup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes', type=int, default=DEFAULT_MINUTES,
            help=f'Only fix tasks stuck longer than this many minutes (default {DEFAULT_MINUTES})',
        )

    def handle(self, *args, **options):
        from production_ledger.models import MediaAsset, BackgroundTask
        from production_ledger.constants import IngestionStatus

        minutes = options['minutes']
        cutoff = timezone.now() - datetime.timedelta(minutes=minutes)
        total_fixed = 0

        # ── 1. Stuck MediaAsset audio extractions ──────────────────────────
        stuck_assets = MediaAsset.objects.filter(
            ingestion_status__in=[IngestionStatus.PENDING, IngestionStatus.PROCESSING],
            created_at__lt=cutoff,
            asset_type='audio',
        )
        count = stuck_assets.count()
        if count:
            stuck_assets.update(
                ingestion_status=IngestionStatus.FAILED,
                error_message=(
                    'Extraction was interrupted (server restart). '
                    'Please retry audio extraction.'
                ),
            )
            self.stdout.write(self.style.WARNING(
                f'[fix_stuck_tasks] Marked {count} stuck audio asset(s) as FAILED.'
            ))
            total_fixed += count

        # ── 2. Stuck BackgroundTask records ────────────────────────────────
        stuck_tasks = BackgroundTask.objects.filter(
            status__in=[BackgroundTask.STATUS_PENDING, BackgroundTask.STATUS_RUNNING],
            created_at__lt=cutoff,
        )
        count = stuck_tasks.count()
        if count:
            stuck_tasks.update(
                status=BackgroundTask.STATUS_TIMEOUT,
                error_message=(
                    'Task was interrupted by a server restart. '
                    'Please try again.'
                ),
                completed_at=timezone.now(),
            )
            self.stdout.write(self.style.WARNING(
                f'[fix_stuck_tasks] Marked {count} stuck BackgroundTask(s) as TIMEOUT.'
            ))
            total_fixed += count

        if total_fixed == 0:
            self.stdout.write('[fix_stuck_tasks] No stuck tasks found — all clear.')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'[fix_stuck_tasks] Cleaned up {total_fixed} orphaned task(s) total.'
            ))
