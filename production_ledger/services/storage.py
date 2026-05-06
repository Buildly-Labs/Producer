"""
DigitalOcean Spaces Storage Service.

Provides an S3-compatible interface for uploading, downloading, and managing
media files (video, audio, podcast feeds, rendered shorts) on DO Spaces.

Uses the same variable names as the rest of the project:
    AWS_STORAGE_BUCKET_NAME = 'collab'
    AWS_ACCESS_KEY_ID       = 'DO00MW9V6QPPJKVCGHYA'
    AWS_SECRET_ACCESS_KEY   = os.environ.get("SPACES_SECRET")
    AWS_S3_CUSTOM_DOMAIN    = 'cms-static.nyc3.digitaloceanspaces.com/collab'
    AWS_S3_ENDPOINT_URL     = 'https://cms-static.nyc3.digitaloceanspaces.com'
"""
import hashlib
import logging
import mimetypes
import os
from pathlib import PurePosixPath
from typing import IO, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spaces config — mirrors existing project settings
# ---------------------------------------------------------------------------
AWS_STORAGE_BUCKET_NAME = 'collab'
AWS_ACCESS_KEY_ID       = 'DO00MW9V6QPPJKVCGHYA'
AWS_SECRET_ACCESS_KEY   = os.environ.get('SPACES_SECRET')
AWS_S3_CUSTOM_DOMAIN    = 'cms-static.nyc3.digitaloceanspaces.com' + '/' + AWS_STORAGE_BUCKET_NAME
AWS_S3_ENDPOINT_URL     = 'https://cms-static.nyc3.digitaloceanspaces.com'
_SPACES_REGION          = 'nyc3'


def _get_spaces_config() -> dict:
    return {
        "key": AWS_ACCESS_KEY_ID,
        "secret": AWS_SECRET_ACCESS_KEY or "",
        "region": _SPACES_REGION,
        "bucket": AWS_STORAGE_BUCKET_NAME,
        "endpoint": AWS_S3_ENDPOINT_URL,
        "cdn_endpoint": f"https://{AWS_S3_CUSTOM_DOMAIN}",
    }


def _build_client():
    cfg = _get_spaces_config()
    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=cfg["region"],
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["key"],
        aws_secret_access_key=cfg["secret"],
    )


def _public_url(key: str) -> str:
    """Return the public CDN URL for a Spaces object key."""
    cdn = f"https://{AWS_S3_CUSTOM_DOMAIN}".rstrip("/")
    return f"{cdn}/{key}"


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_file(
    file_obj: IO[bytes],
    key: str,
    content_type: Optional[str] = None,
    public: bool = True,
    extra_metadata: Optional[dict] = None,
) -> str:
    """
    Upload a file-like object to DO Spaces.

    Args:
        file_obj:      Open binary file or BytesIO.
        key:           Destination path/key in the bucket (e.g. "podcasts/ep-001/audio.mp3").
        content_type:  MIME type; auto-detected from key if omitted.
        public:        If True, set object ACL to public-read.
        extra_metadata: Optional dict stored as S3 user metadata.

    Returns:
        Public CDN URL of the uploaded object.
    """
    cfg = _get_spaces_config()
    client = _build_client()

    if not content_type:
        content_type, _ = mimetypes.guess_type(key)
        content_type = content_type or "application/octet-stream"

    put_kwargs: dict = {
        "Bucket": cfg["bucket"],
        "Key": key,
        "Body": file_obj,
        "ContentType": content_type,
    }
    if public:
        put_kwargs["ACL"] = "public-read"
    if extra_metadata:
        put_kwargs["Metadata"] = {str(k): str(v) for k, v in extra_metadata.items()}

    client.put_object(**put_kwargs)
    url = _public_url(key)
    logger.info("Uploaded to DO Spaces: %s → %s", key, url)
    return url


def upload_local_file(
    local_path: str,
    key: str,
    content_type: Optional[str] = None,
    public: bool = True,
    extra_metadata: Optional[dict] = None,
) -> str:
    """
    Upload a local file path to DO Spaces.

    Returns:
        Public CDN URL of the uploaded object.
    """
    with open(local_path, "rb") as fh:
        return upload_file(fh, key, content_type=content_type, public=public, extra_metadata=extra_metadata)


# ---------------------------------------------------------------------------
# Download / presigned
# ---------------------------------------------------------------------------

def download_file(key: str, dest_path: str) -> None:
    """Download an object from DO Spaces to a local path."""
    cfg = _get_spaces_config()
    client = _build_client()
    client.download_file(cfg["bucket"], key, dest_path)
    logger.info("Downloaded from DO Spaces: %s → %s", key, dest_path)


def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """
    Generate a presigned GET URL for a private object.

    Args:
        key:        Object key in the bucket.
        expires_in: Expiry in seconds (default 1 hour).

    Returns:
        Presigned URL string.
    """
    cfg = _get_spaces_config()
    client = _build_client()
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": cfg["bucket"], "Key": key},
        ExpiresIn=expires_in,
    )
    return url


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_file(key: str) -> None:
    """Delete an object from DO Spaces."""
    cfg = _get_spaces_config()
    client = _build_client()
    client.delete_object(Bucket=cfg["bucket"], Key=key)
    logger.info("Deleted from DO Spaces: %s", key)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def episode_audio_key(organization_uuid: str, episode_id: str, filename: str) -> str:
    """Standard key path for episode audio files."""
    return f"producer/{organization_uuid}/episodes/{episode_id}/audio/{filename}"


def episode_video_key(organization_uuid: str, episode_id: str, filename: str) -> str:
    """Standard key path for episode video files."""
    return f"producer/{organization_uuid}/episodes/{episode_id}/video/{filename}"


def short_video_key(organization_uuid: str, episode_id: str, short_id: str, filename: str) -> str:
    """Standard key path for rendered short videos."""
    return f"producer/{organization_uuid}/episodes/{episode_id}/shorts/{short_id}/{filename}"


def podcast_feed_key(organization_uuid: str, show_slug: str) -> str:
    """Standard key path for the RSS podcast feed XML."""
    return f"producer/{organization_uuid}/feeds/{show_slug}/feed.xml"


def media_asset_key(organization_uuid: str, episode_id: str, unique_prefix: str, filename: str) -> str:
    """Standard key path for direct-uploaded media assets."""
    return f"producer/{organization_uuid}/episodes/{episode_id}/media/{unique_prefix}_{filename}"


# ---------------------------------------------------------------------------
# Presigned upload URL (browser → Spaces direct upload)
# ---------------------------------------------------------------------------

def generate_presigned_upload_url(
    key: str,
    content_type: str,
    expires: int = 3600,
) -> dict:
    """
    Generate a presigned PUT URL so the browser can upload directly to
    DO Spaces, bypassing the Django server entirely.

    Args:
        key:          Destination object key in the bucket.
        content_type: MIME type of the file being uploaded.
        expires:      Seconds until the presigned URL expires (default 1 h).

    Returns:
        dict with keys:
            url         — presigned PUT URL to use from the browser
            key         — the object key
            public_url  — CDN URL that will be live after the upload completes
    """
    client = _build_client()
    cfg = _get_spaces_config()

    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": cfg["bucket"],
            "Key": key,
            "ContentType": content_type,
            "ACL": "public-read",
        },
        ExpiresIn=expires,
    )
    return {
        "url": url,
        "key": key,
        "public_url": _public_url(key),
    }


def cover_art_key(organization_uuid: str, show_slug: str, filename: str) -> str:
    """Standard key path for show cover art."""
    return f"producer/{organization_uuid}/shows/{show_slug}/cover-art/{filename}"


# ---------------------------------------------------------------------------
# Checksum helper
# ---------------------------------------------------------------------------

def sha256_of_file(file_obj: IO[bytes]) -> str:
    """Return hex SHA-256 digest of a file-like object (rewinds to start)."""
    file_obj.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: file_obj.read(65536), b""):
        digest.update(chunk)
    file_obj.seek(0)
    return digest.hexdigest()
