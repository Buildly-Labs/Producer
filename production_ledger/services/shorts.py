"""
AI Shorts Generation Service.

Workflow:
  1. AI analyses the episode Transcript to identify high-value clip moments
     (hooks, quotable moments, debate highlights).
  2. Clip moments are stored as ClipMoment + VideoShort (status=QUEUED).
  3. A render step uses ffmpeg to cut the clip from the source video and
     re-encode it for the target aspect ratio (vertical 9:16, square 1:1,
     or horizontal 16:9).
  4. The rendered clip is uploaded to DO Spaces; VideoShort.public_url is set
     and status advances to READY.
  5. The shareable CDN link is returned per short.

Environment variables:
  AI_PROVIDER              — 'openai' | 'digitalocean' (default: digitalocean when
                             DIGITALOCEAN_LLM_API_KEY is set, else mock)
  DIGITALOCEAN_LLM_API_KEY — DigitalOcean GenAI API key (preferred)
  DIGITALOCEAN_LLM_ENDPOINT — DigitalOcean GenAI base URL
  AI_API_KEY               — OpenAI key (used when AI_PROVIDER=openai)
  AI_MODEL                 — Chat model for clip identification (default: gpt-4o)
  SHORTS_MAX_CLIPS         — Max clips to identify per episode (default: 5)
  SHORTS_MIN_DURATION      — Minimum clip duration in seconds (default: 20)
  SHORTS_MAX_DURATION      — Maximum clip duration in seconds (default: 90)

ffmpeg must be available on PATH for rendering.
"""
import json
import logging
import os
import subprocess
import tempfile
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

SHORTS_MAX_CLIPS = int(os.environ.get("SHORTS_MAX_CLIPS", "5"))
SHORTS_MIN_DURATION = int(os.environ.get("SHORTS_MIN_DURATION", "20"))
SHORTS_MAX_DURATION = int(os.environ.get("SHORTS_MAX_DURATION", "90"))


# ---------------------------------------------------------------------------
# AI clip identification
# ---------------------------------------------------------------------------

_IDENTIFY_PROMPT = """\
You are a podcast producer specialising in short-form video. Given the transcript
segments below, identify the {max_clips} most compelling moments that would make
engaging short-form clips (TikTok / Instagram Reels / YouTube Shorts).

Each clip must:
- Be between {min_dur}–{max_dur} seconds long.
- Start and end at natural speech boundaries.
- Have a strong hook in the first 3 seconds.
- Be self-contained and understandable without watching the full episode.

Return a JSON array (no extra text) with exactly this schema:
[
  {{
    "start_seconds": 42.5,
    "end_seconds": 87.0,
    "title": "Short punchy title (max 60 chars)",
    "hook": "One-sentence hook / teaser (max 120 chars)",
    "caption": "Platform caption with context (max 280 chars)",
    "hashtags": ["#AI", "#podcast"],
    "priority": "gold|silver|bronze"
  }},
  ...
]

TRANSCRIPT SEGMENTS:
{segments}
"""


class _MockClipIdentifier:
    def identify(self, transcript, max_clips: int, min_dur: int, max_dur: int) -> list[dict]:
        """Return deterministic mock clips for development."""
        return [
            {
                "start_seconds": 30.0,
                "end_seconds": 60.0,
                "title": "The moment everything changed",
                "hook": "Nobody expected this answer about AI.",
                "caption": "This is a placeholder short clip. Real AI clip detection will replace this.",
                "hashtags": ["#AI", "#podcast", "#tech"],
                "priority": "gold",
            },
            {
                "start_seconds": 90.0,
                "end_seconds": 125.0,
                "title": "What experts actually think",
                "hook": "The real story behind AI in 2026.",
                "caption": "Another placeholder short clip from mock provider.",
                "hashtags": ["#AI", "#future"],
                "priority": "silver",
            },
        ][:max_clips]


class _OpenAIClipIdentifier:
    def __init__(self, api_key: str, model: str, base_url: str = None):
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("openai package is required. Run: pip install openai") from exc
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)
        self.model = model

    def identify(self, transcript, max_clips: int, min_dur: int, max_dur: int) -> list[dict]:
        # Build a condensed segment list for the prompt
        normalized = transcript.normalized_json or {}
        segs = normalized.get("segments", [])
        if not segs:
            # Fall back to plain text split into rough chunks
            words = transcript.raw_text.split()
            chunk_size = max(1, len(words) // 20)
            segs = [
                {"start": i * 30, "end": (i + 1) * 30, "text": " ".join(words[i * chunk_size:(i + 1) * chunk_size])}
                for i in range(min(20, len(words) // chunk_size + 1))
            ]

        segment_text = "\n".join(
            f"[{s.get('start', 0):.1f}s → {s.get('end', 0):.1f}s] {s.get('text', '')}"
            for s in segs
        )

        prompt = _IDENTIFY_PROMPT.format(
            max_clips=max_clips,
            min_dur=min_dur,
            max_dur=max_dur,
            segments=segment_text,
        )

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        try:
            parsed = json.loads(raw)
            # Support both {"clips": [...]} and bare [...]
            if isinstance(parsed, dict):
                clips = parsed.get("clips") or parsed.get("moments") or list(parsed.values())[0]
            else:
                clips = parsed
            return clips[:max_clips]
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise RuntimeError(f"AI returned invalid JSON for clip identification: {exc}\nRaw: {raw}") from exc


def _get_identifier():
    explicit = os.environ.get("AI_PROVIDER", "").lower()
    do_key = os.environ.get("DIGITALOCEAN_LLM_API_KEY", "")

    if explicit == "openai":
        return _OpenAIClipIdentifier(
            api_key=os.environ["AI_API_KEY"],
            model=os.environ.get("AI_MODEL", "gpt-4o"),
        )

    if explicit == "digitalocean" or (not explicit and do_key):
        endpoint = os.environ.get(
            "DIGITALOCEAN_LLM_ENDPOINT",
            "https://api.digitalocean.com/v2/gen-ai",
        )
        return _OpenAIClipIdentifier(
            api_key=do_key,
            model=os.environ.get("AI_MODEL", "gpt-4o"),
            base_url=endpoint,
        )

    return _MockClipIdentifier()


# ---------------------------------------------------------------------------
# FFmpeg rendering
# ---------------------------------------------------------------------------

_ASPECT_FILTERS = {
    "9:16": "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920:flags=lanczos",
    "1:1":  "crop='min(iw,ih)':'min(ih,iw)',scale=1080:1080:flags=lanczos",
    "16:9": "scale=1920:1080:flags=lanczos",
}


def _render_clip(source_path: str, start_seconds: float, end_seconds: float, aspect_ratio: str, out_path: str) -> None:
    """
    Use ffmpeg to cut and re-encode a clip.

    Args:
        source_path:   Local path to the source video.
        start_seconds: Clip start in seconds.
        end_seconds:   Clip end in seconds.
        aspect_ratio:  One of '9:16', '1:1', '16:9'.
        out_path:      Destination path for the rendered mp4.
    """
    vf = _ASPECT_FILTERS.get(aspect_ratio, _ASPECT_FILTERS["9:16"])
    duration = end_seconds - start_seconds

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_seconds),
        "-i", source_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed: {result.stderr[-1000:]}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def identify_and_queue_shorts(
    episode,
    transcript=None,
    aspect_ratio: str = "9:16",
    max_clips: int = SHORTS_MAX_CLIPS,
    user=None,
) -> list:
    """
    Use AI to identify compelling clip moments and queue VideoShort objects.

    Does NOT render yet — call ``render_short`` for each queued short.

    Args:
        episode:      Episode model instance.
        transcript:   Transcript instance (uses latest if omitted).
        aspect_ratio: '9:16', '1:1', or '16:9'.
        max_clips:    Max number of shorts to create.
        user:         Django user for audit trail.

    Returns:
        List of VideoShort instances (status=QUEUED).
    """
    from ..constants import ArtifactType, ApprovalStatus, ClipPriority, ShortAspectRatio, ShortStatus  # noqa: PLC0415
    from ..models import AIArtifact, ClipMoment, VideoShort  # noqa: PLC0415

    if transcript is None:
        transcript = episode.transcripts.order_by("-revision").first()
        if transcript is None:
            raise RuntimeError(f"Episode '{episode.title}' has no transcripts. Transcribe first.")

    identifier = _get_identifier()
    clips = identifier.identify(
        transcript,
        max_clips=max_clips,
        min_dur=SHORTS_MIN_DURATION,
        max_dur=SHORTS_MAX_DURATION,
    )

    # Store an AIArtifact for provenance
    _do_key = os.environ.get("DIGITALOCEAN_LLM_API_KEY", "")
    _explicit = os.environ.get("AI_PROVIDER", "").lower()
    _resolved_provider = _explicit or ("digitalocean" if _do_key else "mock")

    artifact = AIArtifact.objects.create(
        episode=episode,
        organization_uuid=episode.organization_uuid,
        artifact_type=ArtifactType.SHORTS,
        input_prompt=f"Identify {max_clips} shorts for episode: {episode.title}",
        input_context_refs={"transcript_id": str(transcript.id)},
        output_text=json.dumps(clips, indent=2),
        provider=_resolved_provider,
        model=os.environ.get("AI_MODEL", "gpt-4o"),
        params={"max_clips": max_clips},
        approval_status=ApprovalStatus.PENDING,
        transparency_summary=f"AI-identified {len(clips)} short clip moments",
        created_by=user,
        updated_by=user,
    )

    priority_map = {
        "gold": ClipPriority.GOLD,
        "silver": ClipPriority.SILVER,
        "bronze": ClipPriority.BRONZE,
    }

    video_shorts = []
    for clip in clips:
        start_ms = int(float(clip.get("start_seconds", 0)) * 1000)
        end_ms = int(float(clip.get("end_seconds", 0)) * 1000)

        # Create a ClipMoment for the timeline
        clip_moment = ClipMoment.objects.create(
            episode=episode,
            transcript=transcript,
            organization_uuid=episode.organization_uuid,
            start_ms=start_ms,
            end_ms=end_ms,
            title=clip.get("title", "Untitled short"),
            hook=clip.get("hook", ""),
            caption_draft=clip.get("caption", ""),
            tags=clip.get("hashtags", []),
            priority=priority_map.get(clip.get("priority", "silver"), ClipPriority.SILVER),
            created_by=user,
            updated_by=user,
        )

        short = VideoShort.objects.create(
            episode=episode,
            clip_moment=clip_moment,
            organization_uuid=episode.organization_uuid,
            title=clip.get("title", "Untitled short"),
            caption=clip.get("caption", ""),
            hashtags=clip.get("hashtags", []),
            start_ms=start_ms,
            end_ms=end_ms,
            aspect_ratio=aspect_ratio,
            status=ShortStatus.QUEUED,
            ai_caption_artifact=artifact,
            created_by=user,
            updated_by=user,
        )
        video_shorts.append(short)

    logger.info(
        "Queued %d VideoShort(s) for episode '%s'",
        len(video_shorts), episode.title,
    )
    return video_shorts


def render_short(video_short, source_video_path: Optional[str] = None, user=None) -> str:
    """
    Render a single VideoShort using ffmpeg and upload to DO Spaces.

    Args:
        video_short:       VideoShort model instance (must be QUEUED or FAILED).
        source_video_path: Local path to source video. If omitted, downloads
                           from the episode's primary MediaAsset.
        user:              Django user for audit trail.

    Returns:
        Public CDN URL of the rendered short.
    """
    from . import storage  # noqa: PLC0415
    from ..constants import ShortStatus  # noqa: PLC0415

    video_short.status = ShortStatus.RENDERING
    video_short.render_started_at = timezone.now()
    video_short.updated_by = user
    video_short.save(update_fields=["status", "render_started_at", "updated_by"])

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            # ── 1. Resolve source video path ──────────────────────────────
            if source_video_path is None:
                source_video_path = _download_source_video(video_short.episode, tmp_dir)

            # ── 2. Render the clip ─────────────────────────────────────────
            start_s = video_short.start_ms / 1000.0
            end_s = video_short.end_ms / 1000.0
            ratio = video_short.aspect_ratio or "9:16"
            out_filename = f"short_{video_short.id}.mp4"
            out_path = os.path.join(tmp_dir, out_filename)

            _render_clip(source_video_path, start_s, end_s, ratio, out_path)

            # ── 3. Upload to DO Spaces ────────────────────────────────────
            video_short.status = ShortStatus.UPLOADING
            video_short.save(update_fields=["status"])

            spaces_key = storage.short_video_key(
                str(video_short.organization_uuid),
                str(video_short.episode_id),
                str(video_short.id),
                out_filename,
            )
            public_url = storage.upload_local_file(
                out_path,
                spaces_key,
                content_type="video/mp4",
                public=True,
                extra_metadata={
                    "episode-id": str(video_short.episode_id),
                    "short-id": str(video_short.id),
                },
            )

            # ── 4. Record final state ──────────────────────────────────────
            file_size = os.path.getsize(out_path)
            duration_s = (video_short.end_ms - video_short.start_ms) / 1000.0

        video_short.status = ShortStatus.READY
        video_short.spaces_key = spaces_key
        video_short.public_url = public_url
        video_short.file_size = file_size
        video_short.duration_seconds = duration_s
        video_short.render_completed_at = timezone.now()
        video_short.error_message = ""
        video_short.updated_by = user
        video_short.save()

        logger.info("VideoShort '%s' rendered: %s", video_short.title, public_url)
        return public_url

    except Exception as exc:
        video_short.status = ShortStatus.FAILED
        video_short.error_message = str(exc)
        video_short.updated_by = user
        video_short.save(update_fields=["status", "error_message", "updated_by"])
        logger.exception("Failed to render VideoShort %s", video_short.pk)
        raise


def render_all_queued_shorts(episode, source_video_path: Optional[str] = None, user=None) -> list[dict]:
    """
    Render all QUEUED VideoShorts for an episode.

    Args:
        episode:           Episode model instance.
        source_video_path: Local path to source video (downloaded once, shared).
        user:              Django user for audit trail.

    Returns:
        List of dicts: [{short_id, title, status, public_url, error}, ...]
    """
    from ..constants import ShortStatus  # noqa: PLC0415

    queued = list(episode.video_shorts.filter(status=ShortStatus.QUEUED))
    if not queued:
        logger.info("No QUEUED shorts for episode '%s'", episode.title)
        return []

    # If source_video_path not provided, download once and share
    own_tmp = None
    if source_video_path is None:
        import tempfile as _tf  # noqa: PLC0415
        own_tmp = _tf.mkdtemp()
        try:
            source_video_path = _download_source_video(episode, own_tmp)
        except Exception as exc:
            # Clean up and propagate
            import shutil  # noqa: PLC0415
            shutil.rmtree(own_tmp, ignore_errors=True)
            raise RuntimeError(f"Could not download source video for episode '{episode.title}': {exc}") from exc

    results = []
    for short in queued:
        result = {"short_id": str(short.id), "title": short.title, "error": None}
        try:
            url = render_short(short, source_video_path=source_video_path, user=user)
            result["status"] = ShortStatus.READY
            result["public_url"] = url
        except Exception as exc:
            result["status"] = ShortStatus.FAILED
            result["public_url"] = None
            result["error"] = str(exc)
        results.append(result)

    if own_tmp:
        import shutil  # noqa: PLC0415
        shutil.rmtree(own_tmp, ignore_errors=True)

    return results


# ---------------------------------------------------------------------------
# Internal: source video resolver
# ---------------------------------------------------------------------------

def _download_source_video(episode, tmp_dir: str) -> str:
    """
    Locate and return a local path to the episode's primary video asset.
    Downloads from DO Spaces / external URL if needed.
    """
    from ..constants import AssetType  # noqa: PLC0415

    video_assets = episode.media_assets.filter(asset_type=AssetType.VIDEO).order_by("created_at")
    if not video_assets.exists():
        raise RuntimeError(f"Episode '{episode.title}' has no video MediaAsset. Upload a video first.")

    asset = video_assets.first()

    if asset.file and hasattr(asset.file, "path"):
        return asset.file.path

    if asset.external_url:
        import urllib.request  # noqa: PLC0415
        ext = os.path.splitext(asset.external_url.split("?")[0])[-1] or ".mp4"
        dest = os.path.join(tmp_dir, f"source_video{ext}")
        urllib.request.urlretrieve(asset.external_url, dest)  # noqa: S310
        return dest

    raise RuntimeError(f"MediaAsset {asset.id} has neither a file nor an external_url.")
