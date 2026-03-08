"""
Audio pipeline — concatenates MP3 segments with transition SFX.
Directly adapted from openclaw-knowledge-radio/src/outputs/audio.py
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

PLAYBACK_ATEMPO = float(os.environ.get("PODCAST_ATEMPO", "1.0"))  # 1.0 = no speedup for science podcast
THRESHOLD_BYTES = int(10.0 * 1024 * 1024)
TARGET_BYTES = int(9.9 * 1024 * 1024)


def build_transition_sfx(out_dir: Path) -> Path:
    """Generate a short transition cue (C + E musical interval)."""
    sfx = out_dir / "transition_sfx.mp3"
    if sfx.exists():
        sfx.unlink(missing_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=1.2",
        "-f", "lavfi", "-i", "sine=frequency=1046:duration=0.12",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=0.06",
        "-f", "lavfi", "-i", "sine=frequency=1318:duration=0.12",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=1.2",
        "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[a]",
        "-map", "[a]", "-ar", "24000", "-ac", "1",
        "-codec:a", "libmp3lame", "-q:a", "4",
        str(sfx),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sfx


def get_duration(mp3_path: Path) -> float:
    """Frame-accurate MP3 duration via mutagen, fallback to ffprobe."""
    try:
        from mutagen.mp3 import MP3
        return MP3(str(mp3_path)).info.length
    except Exception:
        pass
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_path)]
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)


def concat_with_transitions(segment_files: List[Path], out_mp3: Path,
                             atempo: float = PLAYBACK_ATEMPO) -> List[dict]:
    """
    Concatenate segment MP3s with transition SFX between them.
    Returns list of {title, timestamp_sec} for episode index / seeking.
    """
    non_empty = [s for s in segment_files if s and s.exists() and s.stat().st_size > 1000]
    if not non_empty:
        raise RuntimeError("No valid MP3 segments to merge")

    sfx = build_transition_sfx(out_mp3.parent)
    sfx_duration = get_duration(sfx)

    # Build sequence and timestamps
    sequence: List[Path] = []
    timestamps = []
    cursor = 0.0

    for i, seg in enumerate(non_empty):
        timestamps.append(cursor)
        dur = get_duration(seg)
        sequence.append(seg)
        cursor += dur
        if i < len(non_empty) - 1:
            sequence.append(sfx)
            cursor += sfx_duration

    # Write concat list
    list_file = out_mp3.parent / "ffmpeg_concat_list.txt"
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in sequence))

    # Concatenate
    filter_str = f"atempo={atempo}" if atempo != 1.0 else "anull"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-filter:a", filter_str,
        "-codec:a", "libmp3lame", "-q:a", "4",
        str(out_mp3),
    ]
    subprocess.run(cmd, check=True)
    logger.info(f"Audio: merged {len(non_empty)} segments → {out_mp3.name} "
                f"({out_mp3.stat().st_size / 1024 / 1024:.1f} MB)")

    return timestamps
