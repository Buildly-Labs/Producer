"""
YouTube Data API v3 integration for automated video podcast uploads.

Flow:
  1. Show admin connects YouTube via OAuth 2.0 (see YoutubeOAuthStartView /
     YoutubeOAuthCallbackView in views.py).  The refresh_token is stored in
     PodcastFeedConfig.
  2. On "Publish to YouTube" action, this service streams the video from DO
     Spaces and uploads it via the resumable-upload endpoint.
  3. The returned YouTube video ID is stored in PodcastDistribution.platform_url.

Required Google Cloud setup:
  - YouTube Data API v3 enabled on the project.
  - OAuth 2.0 credentials (Web application type).
  - Authorised redirect URI = <APP_BASE_URL>/ledger/shows/<pk>/youtube/callback/
"""

import logging
import urllib.request

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

log = logging.getLogger(__name__)

YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
TOKEN_URI = 'https://oauth2.googleapis.com/token'
AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'

# Category IDs: 22 = People & Blogs, 27 = Education, 28 = Science & Technology
DEFAULT_CATEGORY_ID = '22'


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _credentials_from_config(feed_config):
    """Return a refreshed google.oauth2.credentials.Credentials object."""
    from django.conf import settings  # noqa: PLC0415

    client_id = feed_config.youtube_client_id or getattr(settings, 'YOUTUBE_CLIENT_ID', '')
    client_secret = feed_config.youtube_client_secret or getattr(settings, 'YOUTUBE_CLIENT_SECRET', '')

    if not client_id or not client_secret:
        raise ValueError(
            "YouTube client ID / secret not configured. "
            "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in settings, "
            "or enter them in Show Settings."
        )
    if not feed_config.youtube_refresh_token:
        raise ValueError(
            "YouTube not connected for this show. "
            "Go to Show Settings → YouTube and click 'Connect YouTube'."
        )

    creds = Credentials(
        token=None,
        refresh_token=feed_config.youtube_refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
    )
    # Force a refresh so we have a valid access token
    creds.refresh(GoogleRequest())
    return creds


def get_youtube_service(feed_config):
    """Return an authenticated YouTube API service resource."""
    creds = _credentials_from_config(feed_config)
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------------------
# OAuth helpers (used by views)
# ---------------------------------------------------------------------------

def build_oauth_flow(feed_config, redirect_uri):
    """Return a google_auth_oauthlib Flow ready to generate an auth URL."""
    from google_auth_oauthlib.flow import Flow  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    client_id = feed_config.youtube_client_id or getattr(settings, 'YOUTUBE_CLIENT_ID', '')
    client_secret = feed_config.youtube_client_secret or getattr(settings, 'YOUTUBE_CLIENT_SECRET', '')

    if not client_id or not client_secret:
        raise ValueError("YouTube client credentials are not configured.")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=YOUTUBE_SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow


def fetch_channel_info(feed_config):
    """Return (channel_id, channel_name) for the connected account."""
    service = get_youtube_service(feed_config)
    resp = service.channels().list(part='snippet', mine=True).execute()
    items = resp.get('items', [])
    if not items:
        return '', ''
    item = items[0]
    return item['id'], item['snippet']['title']


# ---------------------------------------------------------------------------
# Video upload
# ---------------------------------------------------------------------------

def upload_episode_to_youtube(episode, video_url, feed_config, privacy=None):
    """
    Download the video from *video_url* (DO Spaces public URL) and upload it
    to YouTube via resumable upload.

    Returns the YouTube video ID string.
    Raises ValueError / HttpError on failure.
    """
    privacy = privacy or feed_config.youtube_default_privacy or 'public'

    # Build metadata from episode data
    title = episode.title[:100]  # YouTube title max 100 chars

    # Description: show notes → plain text + guest list + website
    description = _build_description(episode, feed_config)

    service = get_youtube_service(feed_config)

    # Stream the video from DO Spaces into the upload
    log.info("YouTube upload: downloading %s for episode %s", video_url, episode.pk)
    req = urllib.request.Request(video_url, headers={'User-Agent': 'ForgeMarketing/1.0'})
    with urllib.request.urlopen(req, timeout=30) as video_stream:  # noqa: S310
        media = MediaIoBaseUpload(
            video_stream,
            mimetype='video/mp4',
            chunksize=8 * 1024 * 1024,  # 8 MB chunks
            resumable=True,
        )

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'categoryId': DEFAULT_CATEGORY_ID,
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': False,
            },
        }

        insert_request = service.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media,
        )

        log.info("YouTube upload: starting resumable upload for '%s'", title)
        response = None
        while response is None:
            status, response = insert_request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                log.info("YouTube upload progress: %d%%", pct)

    video_id = response.get('id', '')
    log.info("YouTube upload complete: video ID %s", video_id)
    return video_id


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _build_description(episode, feed_config):
    """Build a YouTube description from episode show notes and guest info."""
    import re  # noqa: PLC0415

    parts = []
    show_note = getattr(episode, 'show_note_final', None)
    if show_note and show_note.markdown:
        plain = re.sub(r'#+\s*', '', show_note.markdown)
        plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)
        plain = re.sub(r'\*(.+?)\*', r'\1', plain)
        plain = re.sub(r'!\[.*?\]\(.*?\)', '', plain)
        plain = re.sub(r'\[(.+?)\]\((https?://[^\)]+)\)', r'\1: \2', plain)
        plain = re.sub(r'^\s*[-*+]\s+', '', plain, flags=re.MULTILINE)
        parts.append(plain.strip())

    guests = list(episode.episode_guests.select_related('guest').all())
    if guests:
        guest_lines = ['Guests:']
        for eg in guests:
            g = eg.guest
            line = g.name
            if g.title or g.org:
                line += f" — {', '.join(filter(None, [g.title, g.org]))}"
            if isinstance(g.links, dict):
                for k, v in g.links.items():
                    if v and v.startswith('http'):
                        line += f'\n  {k}: {v}'
            guest_lines.append(line)
        parts.append('\n'.join(guest_lines))

    try:
        if feed_config and feed_config.website_url:
            parts.append(f'Learn more: {feed_config.website_url}')
    except Exception:
        pass

    description = '\n\n'.join(parts)
    # YouTube description max is 5000 chars
    return description[:5000]
