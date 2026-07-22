"""
Management command: render_pending_shorts

Renders all QUEUED VideoShorts across all (or specified) episodes and
uploads them to DO Spaces.

Usage:
    python manage.py render_pending_shorts
    python manage.py render_pending_shorts --episode <uuid>
    python manage.py render_pending_shorts --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from production_ledger.constants import ShortStatus
from production_ledger.models import Episode, VideoShort
from production_ledger.services.shorts import render_all_queued_shorts


class Command(BaseCommand):
    help = "Render all QUEUED VideoShorts and upload them to DO Spaces."

    def add_arguments(self, parser):
        parser.add_argument(
            '--episode',
            type=str,
            metavar='UUID',
            help='Limit to a single episode UUID.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List queued shorts without rendering.',
        )

    def handle(self, *args, **options):
        episode_id = options.get('episode')
        dry_run = options.get('dry_run')

        if episode_id:
            try:
                episodes = [Episode.objects.get(pk=episode_id)]
            except Episode.DoesNotExist:
                raise CommandError(f"Episode '{episode_id}' not found.")
        else:
            # Only episodes that actually have queued shorts
            episode_ids = (
                VideoShort.objects
                .filter(status=ShortStatus.QUEUED)
                .values_list('episode_id', flat=True)
                .distinct()
            )
            episodes = list(Episode.objects.filter(pk__in=episode_ids))

        if not episodes:
            self.stdout.write(self.style.SUCCESS("No episodes with QUEUED shorts found."))
            return

        total_queued = sum(
            ep.video_shorts.filter(status=ShortStatus.QUEUED).count()
            for ep in episodes
        )
        self.stdout.write(f"Found {total_queued} QUEUED short(s) across {len(episodes)} episode(s).")

        if dry_run:
            for ep in episodes:
                queued = ep.video_shorts.filter(status=ShortStatus.QUEUED)
                for s in queued:
                    self.stdout.write(f"  [{ep.title}] {s.title} ({s.start_formatted}–{s.end_formatted})")
            return

        total_ok = 0
        total_fail = 0
        for ep in episodes:
            self.stdout.write(f"\nRendering shorts for: {ep.title}")
            results = render_all_queued_shorts(ep)
            for r in results:
                if r['status'] == ShortStatus.READY:
                    total_ok += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ {r['title']}  →  {r['public_url']}")
                    )
                else:
                    total_fail += 1
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ {r['title']}  →  {r['error']}")
                    )

        self.stdout.write(f"\nDone. {total_ok} rendered, {total_fail} failed.")
