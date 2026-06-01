"""ffmpeg screenshot command builders."""

from __future__ import annotations

from pathlib import Path


def build_first_frame_command(
    *,
    ffmpeg_path: str,
    video_path: Path,
    output_path: Path,
) -> list[str]:
    """Return an ffmpeg command that extracts the first video frame."""
    return [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(output_path),
    ]


def build_last_frame_command(
    *,
    ffmpeg_path: str,
    video_path: Path,
    output_path: Path,
) -> list[str]:
    """Return an ffmpeg command that extracts a frame near the end of the video."""
    return [
        ffmpeg_path,
        "-y",
        "-sseof",
        "-1",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
