"""
Text-to-Speech service for intro announcement generation.

Primary engine: OpenAI TTS API (tts-1 / tts-1-hd).
Fallback:       System TTS (macOS 'say', Linux espeak-ng).

VibeVoice-TTS was considered but its code was removed from the GitHub repo
in Sept 2025 due to misuse concerns. VibeVoice-Realtime-0.5B requires local
GPU inference and is not practical for a Django application server.
OpenAI TTS provides comparable quality with no local model overhead.

Usage::

    from .tts import generate_intro, VOICES

    path, duration = generate_intro(
        text="Welcome to The Forge Podcast. This episode: Building in Public.",
        voice="onyx",           # or alloy, echo, fable, nova, shimmer
        model="tts-1-hd",      # or "tts-1" (faster, slightly lower quality)
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

# OpenAI voice options for the UI
VOICES = [
    ("alloy",   "Alloy — neutral, balanced"),
    ("echo",    "Echo — clear, professional"),
    ("fable",   "Fable — warm, storytelling"),
    ("onyx",    "Onyx — deep, authoritative"),
    ("nova",    "Nova — bright, energetic"),
    ("shimmer", "Shimmer — soft, conversational"),
]

MODELS = [
    ("tts-1",    "Standard — faster"),
    ("tts-1-hd", "High Definition — richer audio"),
]

DEFAULT_VOICE = "onyx"
DEFAULT_MODEL = "tts-1-hd"


def generate_intro(
    text: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    speed: float = 1.0,
) -> tuple[Path, float]:
    """
    Generate a TTS MP3 from *text*.

    Returns:
        (path, duration_seconds) — caller is responsible for deleting path.

    Raises:
        RuntimeError if both OpenAI and system TTS fail.
    """
    if not text or not text.strip():
        raise ValueError("Intro text cannot be empty.")

    # Try OpenAI first
    try:
        return _openai_tts(text, voice, model, speed)
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


def _openai_tts(text: str, voice: str, model: str, speed: float) -> tuple[Path, float]:
    from openai import OpenAI  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured.")

    client = OpenAI(api_key=api_key)

    # Validate voice
    valid_voices = [v for v, _ in VOICES]
    if voice not in valid_voices:
        voice = DEFAULT_VOICE

    # Clamp speed to OpenAI's supported range
    speed = max(0.25, min(4.0, float(speed)))

    tmp_path = Path(tempfile.mktemp(prefix="forge_tts_", suffix=".mp3"))

    response = client.audio.speech.create(
        model=model,
        voice=voice,  # type: ignore[arg-type]
        input=text,
        response_format="mp3",
        speed=speed,
    )
    response.stream_to_file(str(tmp_path))

    duration = _probe_duration(tmp_path)
    logger.info("OpenAI TTS generated: %s (%.1fs, voice=%s, model=%s)", tmp_path, duration, voice, model)
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
