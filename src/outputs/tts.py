"""
TTS pipeline — converts text to MP3 using Edge TTS (free, no key).
Falls back to gTTS if Edge fails.
Adapted from openclaw-knowledge-radio/src/outputs/tts_edge.py
"""

import asyncio
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import edge_tts
from gtts import gTTS

logger = logging.getLogger(__name__)

FALLBACK_VOICES = [
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
    "en-US-GuyNeural",
    "en-US-AriaNeural",
]


def synthesize(text: str, out_path: Path, voice: str = "en-GB-RyanNeural",
               rate: str = "+20%", retries: int = 3) -> bool:
    """
    Convert text to MP3. Returns True if successful.
    Tries Edge TTS first, falls back to gTTS.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = _clean_for_tts(text)

    if not cleaned.strip():
        logger.warning(f"Empty text for {out_path.name}, skipping")
        return False

    rate = _normalize_rate(rate)

    # Try Edge TTS across fallback voices
    voices = [voice] + [v for v in FALLBACK_VOICES if v != voice]
    for v in voices:
        for attempt in range(retries):
            try:
                asyncio.run(_edge_tts(cleaned, out_path, v, rate))
                if _validate_mp3(out_path):
                    logger.debug(f"Edge TTS OK: {out_path.name} ({v})")
                    return True
            except Exception as e:
                logger.warning(f"Edge TTS failed ({v}, attempt {attempt+1}): {e}")

    # Fallback: gTTS
    try:
        logger.info(f"Falling back to gTTS for {out_path.name}")
        tts = gTTS(text=cleaned, lang="en", slow=False)
        tts.save(str(out_path))
        if _validate_mp3(out_path):
            return True
    except Exception as e:
        logger.error(f"gTTS also failed: {e}")

    return False


async def _edge_tts(text: str, out_path: Path, voice: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


def _validate_mp3(path: Path, min_bytes: int = 5000) -> bool:
    """Check MP3 exists, is big enough, and ffprobe can read it."""
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return path.stat().st_size >= min_bytes


def _normalize_rate(rate: str) -> str:
    s = (rate or "").strip()
    if re.fullmatch(r"[+-]?\d+%", s):
        return s if s.startswith(("+", "-")) else f"+{s}"
    return "+0%"


def _clean_for_tts(text: str) -> str:
    """Remove markdown and URLs that TTS would read literally."""
    # Remove markdown links [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove raw URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    # Remove backtick code
    text = re.sub(r"`[^`]+`", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
