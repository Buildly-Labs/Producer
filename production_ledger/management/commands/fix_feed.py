"""
Management command: fix_feed

Usage:
    python manage.py fix_feed <show-slug> [--dry-run]

For each episode in the show that has an audio MediaAsset but no
PodcastDistribution record, creates SUBMITTED distribution records so the
episode will appear in the RSS feed.

Use --dry-run to preview changes without writing to the database.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Create missing PodcastDistribution records for episodes that have audio assets"

    def add_arguments(self, parser):
        parser.add_argument("show_slug", help="Slug of the show to fix")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be done without making changes",
        )

    def handle(self, *args, **options):
        from production_ledger.models import Show, Episode, PodcastDistribution, MediaAsset
        from production_ledger.constants import DistributionStatus, PodcastPlatform, AssetType

        dry_run = options["dry_run"]
        slug = options["show_slug"]

        try:
            show = Show.objects.get(slug=slug)
        except Show.DoesNotExist:
            raise CommandError(f"Show with slug '{slug}' not found.")

        self.stdout.write(self.style.SUCCESS(f"Show: {show.name}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("  DRY RUN — no changes will be saved\n"))

        all_platforms = [p for p, _ in PodcastPlatform.CHOICES]
        created_total = 0

        for ep in Episode.objects.filter(show=show).order_by("publish_date"):
            # Check if already in feed
            feed_dists = PodcastDistribution.objects.filter(
                episode=ep,
                status__in=[DistributionStatus.SUBMITTED, DistributionStatus.LIVE],
            ).exclude(audio_public_url="")

            if feed_dists.exists():
                self.stdout.write(f"  ✓ {ep.title} — already in feed")
                continue

            # Find best audio asset
            audio_asset = (
                MediaAsset.objects.filter(episode=ep, asset_type=AssetType.AUDIO)
                .exclude(external_url="")
                .order_by("-created_at")
                .first()
            )

            if not audio_asset:
                self.stdout.write(
                    self.style.WARNING(f"  ✗ {ep.title} — no audio asset found, skipping")
                )
                continue

            audio_url = audio_asset.external_url
            self.stdout.write(
                f"  → {ep.title}\n"
                f"    audio: {audio_url[:80]}"
            )

            if not dry_run:
                for platform in all_platforms:
                    PodcastDistribution.objects.update_or_create(
                        episode=ep,
                        platform=platform,
                        defaults={
                            "organization_uuid": ep.organization_uuid,
                            "audio_public_url": audio_url,
                            "audio_spaces_key": getattr(audio_asset, "spaces_key", "") or "",
                            "audio_file_size": audio_asset.file_size or 0,
                            "audio_duration_seconds": audio_asset.duration_seconds or 0,
                            "audio_content_type": audio_asset.content_type or "audio/mpeg",
                            "status": DistributionStatus.SUBMITTED,
                            "submitted_at": timezone.now(),
                        },
                    )
                created_total += 1
                self.stdout.write(
                    self.style.SUCCESS(f"    Created distribution records for {len(all_platforms)} platforms")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"    Would create {len(all_platforms)} distribution records")
                )
                created_total += 1

        if dry_run:
            self.stdout.write(f"\nDry run complete. Would fix {created_total} episode(s).\n")
        else:
            self.stdout.write(f"\nDone. Fixed {created_total} episode(s).\n")
            if created_total > 0:
                self.stdout.write(
                    "RSS feed will auto-rebuild on next request. "
                    "Or run: python manage.py shell -c \"from production_ledger.models import Show; "
                    "from production_ledger.services.distribution import build_and_publish_feed; "
                    f"build_and_publish_feed(Show.objects.get(slug='{slug}'))\""
                )
