"""
Management command: rebuild_podcast_feeds

Regenerates and re-uploads RSS feed XML to DO Spaces for all (or one) shows.

Usage:
    python manage.py rebuild_podcast_feeds
    python manage.py rebuild_podcast_feeds --show <slug>
"""
from django.core.management.base import BaseCommand, CommandError

from production_ledger.models import Show
from production_ledger.services.distribution import build_and_publish_feed


class Command(BaseCommand):
    help = "Rebuild and upload RSS podcast feeds to DO Spaces."

    def add_arguments(self, parser):
        parser.add_argument(
            '--show',
            type=str,
            metavar='SLUG',
            help='Limit to a single show slug.',
        )

    def handle(self, *args, **options):
        show_slug = options.get('show')

        if show_slug:
            try:
                shows = [Show.objects.get(slug=show_slug)]
            except Show.DoesNotExist:
                raise CommandError(f"Show '{show_slug}' not found.")
        else:
            shows = list(Show.objects.all())

        if not shows:
            self.stdout.write("No shows found.")
            return

        for show in shows:
            try:
                feed_url = build_and_publish_feed(show)
                self.stdout.write(self.style.SUCCESS(f"  ✓ {show.slug}  →  {feed_url}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  ✗ {show.slug}  →  {exc}"))
