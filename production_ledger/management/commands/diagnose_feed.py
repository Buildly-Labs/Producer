"""
Management command: diagnose_feed

Usage:
    python manage.py diagnose_feed <show-slug>

Prints a diagnostic table showing all episodes for the show and whether
they have PodcastDistribution records that would appear in the RSS feed.
Also shows any issues that would prevent episodes from appearing.
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Diagnose why episodes may not appear in the RSS feed"

    def add_arguments(self, parser):
        parser.add_argument("show_slug", help="Slug of the show to diagnose")

    def handle(self, *args, **options):
        from production_ledger.models import Show, Episode, PodcastDistribution
        from production_ledger.constants import DistributionStatus

        slug = options["show_slug"]
        try:
            show = Show.objects.get(slug=slug)
        except Show.DoesNotExist:
            raise CommandError(f"Show with slug '{slug}' not found.")

        self.stdout.write(self.style.SUCCESS(f"\nShow: {show.name} (slug={show.slug})"))
        self.stdout.write(f"  org_uuid: {show.organization_uuid}\n")

        episodes = Episode.objects.filter(show=show).order_by("publish_date")
        self.stdout.write(f"Total episodes: {episodes.count()}\n")

        feed_count = 0
        for ep in episodes:
            dists = PodcastDistribution.objects.filter(episode=ep)
            feed_dists = dists.filter(
                status__in=[DistributionStatus.SUBMITTED, DistributionStatus.LIVE]
            ).exclude(audio_public_url="")

            in_feed = feed_dists.exists()
            if in_feed:
                feed_count += 1

            status_str = self.style.SUCCESS("IN FEED") if in_feed else self.style.ERROR("MISSING")
            self.stdout.write(f"\n  [{status_str}] {ep.title} (id={ep.id})")
            self.stdout.write(f"    publish_date: {ep.publish_date}")
            self.stdout.write(f"    distributions total: {dists.count()}")

            for d in dists:
                url_preview = (d.audio_public_url[:60] + "...") if len(d.audio_public_url) > 60 else d.audio_public_url
                self.stdout.write(
                    f"      platform={d.platform}  status={d.status}  "
                    f"audio_url={'(empty)' if not d.audio_public_url else url_preview}"
                )

            if not in_feed:
                reasons = []
                if not dists.exists():
                    reasons.append("No PodcastDistribution records at all — audio was never published through the Publish tab")
                else:
                    bad_status = dists.exclude(status__in=[DistributionStatus.SUBMITTED, DistributionStatus.LIVE])
                    if bad_status.exists():
                        statuses = list(bad_status.values_list("status", flat=True).distinct())
                        reasons.append(f"All distributions have wrong status: {statuses} (need submitted or live)")
                    no_url = dists.filter(audio_public_url="")
                    if no_url.exists():
                        reasons.append("audio_public_url is empty — upload to storage may have failed")
                for r in reasons:
                    self.stdout.write(self.style.WARNING(f"    → {r}"))

        self.stdout.write(f"\nEpisodes that will appear in feed: {feed_count}/{episodes.count()}\n")
