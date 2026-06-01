"""ffmpeg audio extraction command builder."""

from __future__ import annotations

from pathlib import Path


def build_extract_audio_command(
    *,
    ffmpeg_path: str,
    video_path: Path,
    output_path: Path,
) -> list[str]:
    """Return an ffmpeg command that extracts mono 16 kHz PCM audio."""
    return [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]
