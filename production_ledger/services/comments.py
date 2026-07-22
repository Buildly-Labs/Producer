"""
Comments sync service — ingests platform comments into PlatformComment.

Currently implemented:
  - YouTube: uses the per-show OAuth credentials (PodcastFeedConfig) to
    pull commentThreads for each published video distribution.

All other platforms: manual entry via the UI only (no public API available
from Apple Podcasts, Spotify, Amazon Music, etc. as of 2026).
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def sync_youtube_comments(show, max_results: int = 100) -> dict:
    """
    Fetch the latest YouTube comments for every video distribution on *show*.

    Returns a summary dict::

        {
            'created': <int>,   # new PlatformComment rows
            'updated': <int>,   # existing rows updated (like_count etc.)
            'skipped': <int>,   # already up-to-date
            'errors':  [str],   # per-video error messages
        }
    """
    from production_ledger.models import (  # noqa: PLC0415
        PlatformComment, PodcastDistribution,
    )
    from production_ledger.constants import CommentPlatform  # noqa: PLC0415
    from production_ledger.services.youtube import get_youtube_service  # noqa: PLC0415

    try:
        feed_config = show.podcast_feed_config
    except Exception:
        return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': ['No podcast feed config for this show.']}

    if not feed_config.youtube_connected:
        return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': ['YouTube not connected for this show.']}

    yt_dists = PodcastDistribution.objects.filter(
        episode__show=show,
        platform='youtube',
        platform_url__icontains='youtube.com',
    ).select_related('episode')

    if not yt_dists.exists():
        return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    try:
        yt = get_youtube_service(feed_config)
    except Exception as exc:
        return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': [f'YouTube auth failed: {exc}']}

    summary = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    for dist in yt_dists:
        video_id = _extract_video_id(dist.platform_url)
        if not video_id:
            logger.warning("Could not extract video ID from %s", dist.platform_url)
            continue
        try:
            _sync_video_comments(
                yt, video_id,
                show=show, episode=dist.episode,
                max_results=max_results,
                summary=summary,
            )
        except Exception as exc:
            msg = f"YouTube sync error for {dist.platform_url}: {exc}"
            logger.exception(msg)
            summary['errors'].append(msg)

    return summary


def _extract_video_id(url: str) -> str | None:
    """Extract video ID from a YouTube watch URL."""
    import re  # noqa: PLC0415
    m = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url or '')
    return m.group(1) if m else None


def _sync_video_comments(yt_service, video_id, show, episode, max_results, summary):
    """Pull commentThreads for one video and upsert into PlatformComment."""
    from production_ledger.models import PlatformComment  # noqa: PLC0415
    from production_ledger.constants import CommentPlatform  # noqa: PLC0415

    page_token = None
    fetched = 0

    while fetched < max_results:
        batch = min(100, max_results - fetched)
        request = yt_service.commentThreads().list(
            part='snippet,replies',
            videoId=video_id,
            maxResults=batch,
            pageToken=page_token,
            textFormat='plainText',
        )
        resp = request.execute()

        for item in resp.get('items', []):
            top = item['snippet']['topLevelComment']['snippet']
            thread_id = item['id']
            _upsert_comment(
                show=show, episode=episode,
                platform=CommentPlatform.YOUTUBE,
                external_id=thread_id,
                author_name=top.get('authorDisplayName', ''),
                author_channel_url=top.get('authorChannelUrl', ''),
                author_profile_image=top.get('authorProfileImageUrl', ''),
                body=top.get('textDisplay', ''),
                like_count=top.get('likeCount', 0),
                published_at=top.get('publishedAt'),
                parent_external_id=None,
                summary=summary,
            )
            # Inline replies (up to 5 from YouTube API)
            for reply in item.get('replies', {}).get('comments', []):
                rs = reply['snippet']
                _upsert_comment(
                    show=show, episode=episode,
                    platform=CommentPlatform.YOUTUBE,
                    external_id=reply['id'],
                    author_name=rs.get('authorDisplayName', ''),
                    author_channel_url=rs.get('authorChannelUrl', ''),
                    author_profile_image=rs.get('authorProfileImageUrl', ''),
                    body=rs.get('textDisplay', ''),
                    like_count=rs.get('likeCount', 0),
                    published_at=rs.get('publishedAt'),
                    parent_external_id=thread_id,
                    summary=summary,
                )

        fetched += len(resp.get('items', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break


def _upsert_comment(
    show, episode, platform, external_id,
    author_name, author_channel_url, author_profile_image,
    body, like_count, published_at, parent_external_id, summary,
):
    from production_ledger.models import PlatformComment  # noqa: PLC0415

    parent = None
    if parent_external_id:
        parent = PlatformComment.objects.filter(
            platform=platform, external_id=parent_external_id
        ).first()

    parsed_at = None
    if published_at:
        try:
            parsed_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        except ValueError:
            pass

    defaults = {
        'organization_uuid': show.organization_uuid,
        'show':              show,
        'episode':           episode,
        'author_name':           author_name,
        'author_channel_url':    author_channel_url,
        'author_profile_image':  author_profile_image,
        'body':              body,
        'like_count':        like_count,
        'platform_created_at': parsed_at,
        'parent':            parent,
    }

    if not external_id:
        # Cannot upsert without an ID — skip
        summary['skipped'] += 1
        return

    obj, created = PlatformComment.objects.update_or_create(
        platform=platform,
        external_id=external_id,
        defaults=defaults,
    )
    if created:
        summary['created'] += 1
    else:
        summary['updated'] += 1


def post_reply_to_youtube(comment: 'PlatformComment', reply_text: str, user) -> str:
    """
    Post a reply to a YouTube comment thread.

    Returns the new reply's YouTube comment ID.
    Raises RuntimeError on failure.
    """
    from production_ledger.services.youtube import get_youtube_service  # noqa: PLC0415

    feed_config = comment.show.podcast_feed_config
    if not feed_config.youtube_connected:
        raise RuntimeError('YouTube is not connected for this show.')

    yt = get_youtube_service(feed_config)

    # YouTube replies go to commentThreads.insert or comments.insert
    # For a top-level comment, use comments.insert with parentId
    thread_id = comment.external_id
    if comment.parent:
        # Already a reply — reply to the thread of the parent
        thread_id = comment.parent.external_id

    resp = yt.comments().insert(
        part='snippet',
        body={
            'snippet': {
                'parentId': thread_id,
                'textOriginal': reply_text,
            },
        },
    ).execute()

    reply_id = resp.get('id', '')
    return reply_id
