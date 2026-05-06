"""
Transcription Service.

Wraps OpenAI Whisper API (and an optional local ffmpeg pre-processing step)
to produce transcripts from audio/video files.  Results are stored as
production_ledger.models.Transcript objects.

Workflow:
    1. Caller passes a MediaAsset (with a DO Spaces key or a local file path).
    2. Service downloads the media if needed, optionally extracts audio via ffmpeg.
    3. Calls Whisper API (or a mock provider in dev).
    4. Parses the VTT/verbose JSON response into our normalised JSON schema.
    5. Creates and returns a Transcript linked to the episode.

Environment variables:
    AI_PROVIDER       — 'openai' to use real Whisper; anything else → mock
    AI_API_KEY        — OpenAI API key (required for openai provider)
    WHISPER_MODEL     — Whisper model id (default: 'whisper-1')
    WHISPER_LANGUAGE  — ISO-639-1 code to hint language (default: 'en')
"""
import json
import logging
import os
import tempfile
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalised speaker-block schema
# ---------------------------------------------------------------------------
# normalized_json shape:
# {
#   "segments": [
#     {
#       "start": 0.0,        # seconds
#       "end":   4.2,
#       "text":  "Hello world.",
#       "speaker": null,     # populated by diarisation if available
#       "confidence": 0.95
#     },
#     ...
#   ],
#   "provider": "openai",
#   "model": "whisper-1",
#   "language": "en",
#   "duration": 3600.0
# }

def _normalize_whisper_verbose(response: dict, provider: str, model: str) -> dict:
    """Convert OpenAI verbose_json Whisper response to normalised schema."""
    segments = []
    for seg in response.get("segments", []):
        segments.append({
            "start": float(seg.get("start", 0)),
            "end": float(seg.get("end", 0)),
            "text": seg.get("text", "").strip(),
            "speaker": None,
            "confidence": float(seg.get("avg_logprob", 0)),
        })
    return {
        "segments": segments,
        "provider": provider,
        "model": model,
        "language": response.get("language", ""),
        "duration": float(response.get("duration", 0)),
    }


def _build_raw_text(normalized: dict) -> str:
    """Build plain-text transcript from normalised JSON."""
    return "\n".join(s["text"] for s in normalized.get("segments", []) if s.get("text"))


def _overall_confidence(normalized: dict) -> Optional[float]:
    """Average confidence across segments (returns None if no data)."""
    scores = [s["confidence"] for s in normalized.get("segments", []) if s.get("confidence") is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class _MockTranscriptionProvider:
    """Returns deterministic mock transcript — for development / testing."""

    model = "mock-whisper"
    provider = "mock"

    def transcribe(self, audio_path: str, language: str = "en") -> dict:
        duration = 120.0  # fake 2-minute episode
        segments = [
            {"start": 0.0, "end": 5.0, "text": "Welcome to the show."},
            {"start": 5.0, "end": 12.0, "text": "Today we discuss the future of AI."},
            {"start": 12.0, "end": 20.0, "text": "This is placeholder transcription content."},
        ]
        return {
            "segments": segments,
            "provider": self.provider,
            "model": self.model,
            "language": language,
            "duration": duration,
        }


class _OpenAIWhisperProvider:
    """Uses the OpenAI Whisper API (or any OpenAI-compatible endpoint such as DigitalOcean GenAI)."""

    def __init__(self, api_key: str, model: str, language: str, base_url: Optional[str] = None):
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("openai package is required for Whisper transcription. Run: pip install openai") from exc
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)
        self.model = model
        self.language = language
        self.provider = "digitalocean" if base_url else "openai"

    def transcribe(self, audio_path: str, language: str = "en") -> dict:
        with open(audio_path, "rb") as audio_file:
            response = self._client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        # response is a Transcription object; convert to dict
        if hasattr(response, "model_dump"):
            response_dict = response.model_dump()
        else:
            response_dict = dict(response)
        return _normalize_whisper_verbose(response_dict, self.provider, self.model)


def _get_provider():
    # Resolve provider: explicit AI_PROVIDER wins; fall back to digitalocean if
    # DIGITALOCEAN_LLM_API_KEY is present, otherwise mock.
    explicit = os.environ.get("AI_PROVIDER", "").lower()
    do_key = os.environ.get("DIGITALOCEAN_LLM_API_KEY", "")

    if explicit == "openai":
        return _OpenAIWhisperProvider(
            api_key=os.environ["AI_API_KEY"],
            model=os.environ.get("WHISPER_MODEL", "whisper-1"),
            language=os.environ.get("WHISPER_LANGUAGE", "en"),
        )

    if explicit == "digitalocean" or (not explicit and do_key):
        # DigitalOcean GenAI exposes an OpenAI-compatible Whisper endpoint.
        # Use the same _OpenAIWhisperProvider but point at the DO endpoint.
        endpoint = os.environ.get(
            "DIGITALOCEAN_LLM_ENDPOINT",
            "https://api.digitalocean.com/v2/gen-ai",
        )
        return _OpenAIWhisperProvider(
            api_key=do_key,
            model=os.environ.get("WHISPER_MODEL", "whisper-1"),
            language=os.environ.get("WHISPER_LANGUAGE", "en"),
            base_url=endpoint,
        )

    return _MockTranscriptionProvider()


# ---------------------------------------------------------------------------
# Audio extraction helper (requires ffmpeg on PATH)
# ---------------------------------------------------------------------------

def _extract_audio(video_path: str, out_dir: str) -> str:
    """
    Extract audio track from video using ffmpeg.
    Returns path to the extracted mp3 file.
    """
    import subprocess  # noqa: PLC0415
    out_path = os.path.join(out_dir, "audio.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-b:a", "64k",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr}")
    return out_path


def _is_video(path: str) -> bool:
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    return os.path.splitext(path)[1].lower() in video_exts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transcribe_media_asset(media_asset, user=None):
    """
    Transcribe a MediaAsset and create a Transcript.

    Handles:
      - Local file uploads (``media_asset.file``)
      - DO Spaces remote files (``media_asset.external_url`` with spaces key)
      - Video files (extracts audio via ffmpeg first)

    Args:
        media_asset: A production_ledger.models.MediaAsset instance.
        user:        Django user performing the action (for audit).

    Returns:
        A saved production_ledger.models.Transcript instance.

    Raises:
        RuntimeError on transcription / download failure.
    """
    from ..models import IngestionStatus, Transcript  # avoid circular  # noqa: PLC0415

    media_asset.ingestion_status = IngestionStatus.PROCESSING
    media_asset.save(update_fields=["ingestion_status"])

    provider = _get_provider()
    language = os.environ.get("WHISPER_LANGUAGE", "en")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            # ── 1. Resolve the media file path ──────────────────────────────
            if media_asset.file:
                # Django FileField — local or default storage
                media_path = media_asset.file.path
                own_temp = False
            elif media_asset.external_url:
                # Download from URL (DO Spaces or other)
                import urllib.request  # noqa: PLC0415
                ext = os.path.splitext(media_asset.external_url.split("?")[0])[-1] or ".mp4"
                media_path = os.path.join(tmp_dir, f"source{ext}")
                urllib.request.urlretrieve(media_asset.external_url, media_path)  # noqa: S310
                own_temp = True
            else:
                raise RuntimeError("MediaAsset has neither a file nor an external_url.")

            # ── 2. Extract audio from video if needed ───────────────────────
            if _is_video(media_path):
                audio_path = _extract_audio(media_path, tmp_dir)
            else:
                audio_path = media_path

            # ── 3. Transcribe ────────────────────────────────────────────────
            normalized = provider.transcribe(audio_path, language=language)

        # ── 4. Determine next revision number ──────────────────────────────
        existing_revisions = media_asset.episode.transcripts.values_list("revision", flat=True)
        next_revision = max(existing_revisions, default=0) + 1

        raw_text = _build_raw_text(normalized)
        confidence = _overall_confidence(normalized)

        # ── 5. Persist Transcript ───────────────────────────────────────────
        from ..constants import TranscriptFormat, TranscriptSourceType  # noqa: PLC0415

        transcript = Transcript.objects.create(
            episode=media_asset.episode,
            organization_uuid=media_asset.organization_uuid,
            source_type=TranscriptSourceType.UPLOAD,
            format=TranscriptFormat.TXT,
            raw_text=raw_text,
            normalized_json=normalized,
            confidence_overall=confidence,
            revision=next_revision,
            created_from_media_asset=media_asset,
            ingested_by=user,
            created_by=user,
            updated_by=user,
        )

        media_asset.ingestion_status = IngestionStatus.READY
        media_asset.save(update_fields=["ingestion_status"])

        logger.info(
            "Transcript v%d created for episode %s (provider=%s)",
            next_revision,
            media_asset.episode_id,
            normalized.get("provider"),
        )
        return transcript

    except Exception as exc:
        media_asset.ingestion_status = IngestionStatus.FAILED
        media_asset.error_message = str(exc)
        media_asset.save(update_fields=["ingestion_status", "error_message"])
        logger.exception("Transcription failed for MediaAsset %s", media_asset.pk)
        raise


def transcribe_from_spaces_key(episode, spaces_key: str, user=None):
    """
    Convenience helper: transcribe a file already stored in DO Spaces
    without requiring a pre-existing MediaAsset.

    Downloads the file, transcribes it, and creates a Transcript directly.

    Args:
        episode:    production_ledger.models.Episode instance.
        spaces_key: DO Spaces object key.
        user:       Django user for audit trail.

    Returns:
        A saved Transcript instance.
    """
    from .. import services as svc  # noqa: PLC0415
    from ..constants import IngestionStatus, SourceType, AssetType  # noqa: PLC0415
    from ..models import MediaAsset  # noqa: PLC0415

    public_url = svc.storage._public_url(spaces_key)

    media_asset = MediaAsset.objects.create(
        episode=episode,
        organization_uuid=episode.organization_uuid,
        asset_type=AssetType.VIDEO,
        source_type=SourceType.EXTERNAL_LINK,
        external_url=public_url,
        ingestion_status=IngestionStatus.PENDING,
        created_by=user,
        updated_by=user,
    )
    return transcribe_media_asset(media_asset, user=user)
