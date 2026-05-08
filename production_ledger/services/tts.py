"""
Text-to-Speech service for intro announcement generation.

Primary engine: OpenAI TTS API.
  - Best quality:  gpt-4o-mini-tts  (recommended — supports tone/style prompting)
  - Legacy:        tts-1-hd / tts-1  (still available but noticeably more robotic)

Fallback: System TTS (macOS 'say', Linux espeak-ng).

Voice demos: https://openai.fm/

Usage::

    from .tts import generate_intro, VOICES

    path, duration = generate_intro(
        text="Welcome to The Forge Podcast. This episode: Building in Public.",
        voice="coral",
        model="gpt-4o-mini-tts",
        instructions="Warm, enthusiastic podcast host energy.",
    )
    # path is a pathlib.Path to a temp .mp3 — caller deletes it when done
"""

import logging
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice catalogue
# ---------------------------------------------------------------------------
# gpt-4o-mini-tts supports all 13 voices. tts-1 / tts-1-hd support only the
# first 9 (alloy → shimmer). The UI shows the full set; the API call validates.

VOICES = [
    # Recommended for podcasts ↓
    ("coral",   "Coral — warm, conversational  ★ recommended"),
    ("marin",   "Marin — clear, expressive     ★ recommended"),
    ("cedar",   "Cedar — rich, broadcast-ready ★ recommended"),
    ("ash",     "Ash — smooth, authoritative"),
    ("sage",    "Sage — calm, measured"),
    ("verse",   "Verse — dynamic, versatile"),
    ("ballad",  "Ballad — emotive, storytelling"),
    # Classic set (also available on tts-1-hd) ↓
    ("onyx",    "Onyx — deep, professional"),
    ("nova",    "Nova — bright, energetic"),
    ("alloy",   "Alloy — neutral, balanced"),
    ("echo",    "Echo — clear, precise"),
    ("fable",   "Fable — warm, narrative"),
    ("shimmer", "Shimmer — soft, approachable"),
]

MODELS = [
    ("gpt-4o-mini-tts", "GPT-4o Mini TTS — most natural, supports tone control ★"),
    ("tts-1-hd",        "TTS-1 HD — legacy high definition"),
    ("tts-1",           "TTS-1 — legacy standard (faster, lower quality)"),
]

DEFAULT_VOICE = "coral"
DEFAULT_MODEL = "gpt-4o-mini-tts"

# Default tone instructions sent to gpt-4o-mini-tts.
# The model ignores this for tts-1/tts-1-hd (they don't support instructions).
DEFAULT_INSTRUCTIONS = (
    "You are a professional podcast host. Speak with warmth and enthusiasm, "
    "as if welcoming listeners to an exciting new episode. Keep energy high "
    "but conversational — not over-the-top, just genuinely engaging."
)

# Voices that work with legacy models (tts-1 / tts-1-hd)
LEGACY_VOICES = {"alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"}


def generate_intro(
    text: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = 1.0,
    instructions: str | None = None,
) -> tuple[Path, float]:
    """
    Generate a TTS MP3 from *text*.

    ``instructions`` controls speaking style and is forwarded to
    ``gpt-4o-mini-tts`` only (older models ignore it).
    Pass ``None`` to use DEFAULT_INSTRUCTIONS.

    Returns:
        (path, duration_seconds) — caller is responsible for deleting path.

    Raises:
        RuntimeError if both OpenAI and system TTS fail.
    """
    if not text or not text.strip():
        raise ValueError("Intro text cannot be empty.")

    # Try OpenAI first
    try:
        return _openai_tts(text, voice, model, speed, instructions=instructions)
    except Exception as exc:
        logger.warning("OpenAI TTS failed (%s), falling back to system TTS", exc)

    # Fallback: system TTS
    try:
        return _system_tts(text)
    except Exception as exc:
        raise RuntimeError(
            f"TTS generation failed. OpenAI TTS and system TTS both unavailable. "
            f"Last error: {exc}"
        ) from exc


def _openai_tts(
    text: str,
    voice: str,
    model: str,
    speed: float,
    instructions: str | None = None,
) -> tuple[Path, float]:
    from openai import OpenAI  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured.")

    client = OpenAI(api_key=api_key)

    # Validate voice — fall back for legacy models that don't know newer voices
    valid_voices = [v for v, _ in VOICES]
    if voice not in valid_voices:
        voice = DEFAULT_VOICE
    if model in ("tts-1", "tts-1-hd") and voice not in LEGACY_VOICES:
        logger.info("Voice %s not supported by %s; switching to coral", voice, model)
        voice = "coral"

    # Clamp speed to OpenAI's supported range
    speed = max(0.25, min(4.0, float(speed)))

    tmp_path = Path(tempfile.mktemp(prefix="forge_tts_", suffix=".mp3"))

    # gpt-4o-mini-tts supports an instructions field for tone / style control
    kwargs: dict = dict(
        model=model,
        voice=voice,  # type: ignore[arg-type]
        input=text,
        response_format="mp3",
        speed=speed,
    )
    if model == "gpt-4o-mini-tts":
        kwargs["instructions"] = instructions if instructions is not None else DEFAULT_INSTRUCTIONS

    response = client.audio.speech.create(**kwargs)
    response.stream_to_file(str(tmp_path))

    duration = _probe_duration(tmp_path)
    logger.info(
        "OpenAI TTS generated: %s (%.1fs, voice=%s, model=%s)",
        tmp_path, duration, voice, model,
    )
    return tmp_path, duration


def _system_tts(text: str) -> tuple[Path, float]:
    """Platform-native TTS as a last resort."""
    safe_text = text.replace('"', "'")
    tmp_mp3 = Path(tempfile.mktemp(prefix="forge_tts_sys_", suffix=".mp3"))

    if platform.system() == "Darwin":
        aiff = tmp_mp3.with_suffix(".aiff")
        subprocess.run(["say", "-o", str(aiff), safe_text], check=True, timeout=60)
        _ffmpeg_convert(aiff, tmp_mp3)
        aiff.unlink(missing_ok=True)
    else:
        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if not espeak:
            raise RuntimeError("espeak-ng not found.")
        wav = tmp_mp3.with_suffix(".wav")
        subprocess.run([espeak, "-w", str(wav), safe_text], check=True, timeout=60)
        _ffmpeg_convert(wav, tmp_mp3)
        wav.unlink(missing_ok=True)

    duration = _probe_duration(tmp_mp3)
    return tmp_mp3, duration


def _ffmpeg_convert(src: Path, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(src), "-b:a", "128k", "-y", str(dest)],
        check=True, timeout=120,
    )


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip() or "0")
    except Exception:
        return 0.0
