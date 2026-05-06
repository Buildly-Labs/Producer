"""
Podcast Distribution Service.

Generates an RSS 2.0 / iTunes podcast feed for a Show, uploads it to
DO Spaces, and tracks distribution status per episode per platform.

Supported distribution model:
  - All major platforms (Apple, Spotify, Amazon, Google, iHeart, Stitcher,
    Pocket Casts, Overcast, Castbox) are fed via a single RSS feed that is
    hosted on DO Spaces with a public URL.
  - Platforms that support RSS submission receive the feed URL.
  - This service builds and uploads the feed; it also tracks the
    PodcastDistribution records per episode per platform.

Environment variables:
  DO_SPACES_*  — see services/storage.py
  PODCAST_BASE_URL — Optional. Override the public base URL for audio files.

Dependencies:
  feedgen — pip install feedgen
"""
import logging
import os
from datetime import timezone as dt_timezone
from io import BytesIO
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_feed_config(show):
    """Return the PodcastFeedConfig for a show, creating a stub if absent."""
    from ..models import PodcastFeedConfig  # noqa: PLC0415

    config, _ = PodcastFeedConfig.objects.get_or_create(
        show=show,
        defaults={
            "organization_uuid": show.organization_uuid,
            "feed_title": show.name,
            "feed_description": show.description or show.name,
        },
    )
    return config


def _build_rss_feed(show, config, published_distributions):
    """
    Build an RSS feed using feedgen.

    Args:
        show:                    Show model instance.
        config:                  PodcastFeedConfig instance.
        published_distributions: Queryset of PodcastDistribution objects with
                                 audio_public_url set, ordered by episode.publish_date.

    Returns:
        bytes — UTF-8 encoded RSS XML.
    """
    try:
        from feedgen.feed import FeedGenerator  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("feedgen package is required. Run: pip install feedgen") from exc

    fg = FeedGenerator()
    fg.load_extension("podcast")

    feed_title = config.feed_title or show.name
    feed_description = config.feed_description or show.description or feed_title
    author_name = config.author_name or feed_title
    author_email = config.author_email or ""
    language = config.feed_language or "en"
    website_url = config.website_url or ""
    cover_art_url = config.cover_art_url or ""

    fg.id(config.feed_public_url or website_url or f"https://example.com/podcasts/{show.slug}")
    fg.title(feed_title)
    fg.author({"name": author_name, "email": author_email})
    fg.language(language)
    fg.description(feed_description)
    if website_url:
        fg.link(href=website_url, rel="alternate")
    if config.feed_public_url:
        fg.link(href=config.feed_public_url, rel="self")

    fg.podcast.itunes_author(author_name)
    fg.podcast.itunes_summary(feed_description)
    fg.podcast.itunes_category(config.category or "Technology")
    fg.podcast.itunes_explicit("yes" if config.explicit else "no")
    if cover_art_url:
        fg.podcast.itunes_image(cover_art_url)
    if author_email:
        fg.podcast.itunes_owner(name=author_name, email=author_email)

    for dist in published_distributions:
        episode = dist.episode
        if not dist.audio_public_url:
            continue

        fe = fg.add_entry()
        ep_guid = str(episode.id)
        fe.id(ep_guid)
        fe.title(episode.title)

        # Show notes / description
        show_note = getattr(episode, "show_note_final", None)
        ep_description = show_note.markdown if show_note else (episode.title)
        fe.description(ep_description)
        fe.podcast.itunes_summary(ep_description)

        # Enclosure (audio file)
        fe.enclosure(
            url=dist.audio_public_url,
            length=str(dist.audio_file_size or 0),
            type=dist.audio_content_type or "audio/mpeg",
        )
        fe.podcast.itunes_duration(str(dist.audio_duration_seconds or 0))
        fe.podcast.itunes_explicit("yes" if config.explicit else "no")

        # Publish date
        pub_date = None
        if episode.publish_date:
            import datetime  # noqa: PLC0415
            pub_date = datetime.datetime.combine(
                episode.publish_date,
                datetime.time.min,
                tzinfo=dt_timezone.utc,
            )
        if pub_date:
            fe.published(pub_date)

    return fg.rss_str(pretty=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_and_publish_feed(show, user=None) -> str:
    """
    Regenerate and upload the RSS feed XML for a Show to DO Spaces.

    Args:
        show: Show model instance.
        user: Django user for audit trail.

    Returns:
        Public CDN URL of the uploaded feed XML.
    """
    from .. import services as svc  # noqa: PLC0415 — avoid circular
    from ..constants import DistributionStatus  # noqa: PLC0415
    from ..models import PodcastDistribution  # noqa: PLC0415

    config = _get_feed_config(show)

    # Gather published episodes that have audio on DO Spaces
    dists = (
        PodcastDistribution.objects
        .filter(
            episode__show=show,
            status__in=[DistributionStatus.SUBMITTED, DistributionStatus.LIVE],
        )
        .select_related("episode", "episode__show_note_final")
        .exclude(audio_public_url="")
        .order_by("episode__publish_date")
    )

    feed_xml = _build_rss_feed(show, config, dists)

    # Determine key and upload
    from . import storage  # noqa: PLC0415

    feed_key = storage.podcast_feed_key(str(show.organization_uuid), show.slug)
    feed_url = storage.upload_file(
        BytesIO(feed_xml),
        feed_key,
        content_type="application/rss+xml; charset=utf-8",
        public=True,
        extra_metadata={"show-slug": show.slug, "rebuilt-by": str(user) if user else "system"},
    )

    config.feed_spaces_key = feed_key
    config.feed_public_url = feed_url
    config.feed_last_built = timezone.now()
    if user:
        config.updated_by = user
    config.save()

    logger.info("Podcast feed uploaded for show '%s': %s", show.slug, feed_url)
    return feed_url


def publish_episode_audio(episode, audio_file_obj, filename: str, duration_seconds: int = 0, user=None):
    """
    Upload episode audio to DO Spaces and create/update PodcastDistribution
    records for all major platforms.

    Args:
        episode:          Episode model instance.
        audio_file_obj:   Binary file-like object (mp3 or m4a).
        filename:         Original filename (used for content-type detection).
        duration_seconds: Audio duration in seconds.
        user:             Django user for audit trail.

    Returns:
        dict with keys:
          ``audio_url`` — public CDN URL of the audio file
          ``distributions`` — list of PodcastDistribution objects created/updated
    """
    from . import storage  # noqa: PLC0415
    from ..constants import DistributionStatus, PodcastPlatform  # noqa: PLC0415
    from ..models import PodcastDistribution  # noqa: PLC0415

    import mimetypes  # noqa: PLC0415

    content_type, _ = mimetypes.guess_type(filename)
    content_type = content_type or "audio/mpeg"

    # Compute size
    audio_file_obj.seek(0, 2)
    file_size = audio_file_obj.tell()
    audio_file_obj.seek(0)

    # Upload audio
    audio_key = storage.episode_audio_key(str(episode.organization_uuid), str(episode.id), filename)
    audio_url = storage.upload_file(
        audio_file_obj,
        audio_key,
        content_type=content_type,
        public=True,
        extra_metadata={"episode-id": str(episode.id)},
    )

    # Create / update PodcastDistribution records
    all_platforms = [p for p, _ in PodcastPlatform.CHOICES]
    distributions = []
    for platform in all_platforms:
        dist, _ = PodcastDistribution.objects.update_or_create(
            episode=episode,
            platform=platform,
            defaults={
                "organization_uuid": episode.organization_uuid,
                "audio_spaces_key": audio_key,
                "audio_public_url": audio_url,
                "audio_file_size": file_size,
                "audio_duration_seconds": duration_seconds,
                "audio_content_type": content_type,
                "status": DistributionStatus.SUBMITTED,
                "submitted_at": timezone.now(),
                "updated_by": user,
            },
        )
        distributions.append(dist)

    logger.info(
        "Episode audio uploaded for '%s': %s (%d distributions)",
        episode.title, audio_url, len(distributions),
    )
    return {"audio_url": audio_url, "distributions": distributions}


def get_platform_submission_guide(show) -> list[dict]:
    """
    Return a structured guide for submitting the show's RSS feed to each
    major podcast platform.

    Args:
        show: Show model instance.

    Returns:
        List of dicts: [{platform, name, feed_url, submit_url, status}, ...]
    """
    from ..constants import DistributionStatus, PodcastPlatform  # noqa: PLC0415
    from ..models import PodcastDistribution  # noqa: PLC0415

    config = _get_feed_config(show)
    feed_url = config.feed_public_url or "(feed not yet built)"

    # Aggregate per-platform status from all episode distributions
    platform_statuses: dict[str, str] = {}
    for platform, _ in PodcastPlatform.CHOICES:
        dists = PodcastDistribution.objects.filter(
            episode__show=show,
            platform=platform,
        ).values_list("status", flat=True)
        if not dists:
            platform_statuses[platform] = DistributionStatus.PENDING
        elif DistributionStatus.LIVE in dists:
            platform_statuses[platform] = DistributionStatus.LIVE
        elif DistributionStatus.SUBMITTED in dists:
            platform_statuses[platform] = DistributionStatus.SUBMITTED
        else:
            platform_statuses[platform] = list(dists)[0]

    guide = []
    for platform, label in PodcastPlatform.CHOICES:
        guide.append({
            "platform": platform,
            "name": label,
            "feed_url": feed_url,
            "submit_url": PodcastPlatform.SUBMISSION_URLS.get(platform, ""),
            "status": platform_statuses.get(platform, DistributionStatus.PENDING),
        })
    return guide
