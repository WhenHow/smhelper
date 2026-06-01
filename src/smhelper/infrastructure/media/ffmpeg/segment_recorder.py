"""ffmpeg fixed-time segment recorder command builder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smhelper.core.exceptions import SmHelperError


class InvalidSegmentRecorderConfig(SmHelperError):
    """Raised when ffmpeg segment recording cannot be configured."""


@dataclass(frozen=True, slots=True)
class FFmpegSegmentRecorder:
    """Builds the long-running ffmpeg command for fixed-time segmentation."""

    ffmpeg_path: str
    stream_url: str
    output_dir: Path
    segment_time_seconds: int = 60
    output_pattern: str = "segment_%05d.mp4"

    def __post_init__(self) -> None:
        """Validate segment recorder configuration."""
        if self.segment_time_seconds <= 0:
            raise InvalidSegmentRecorderConfig("segment time must be positive")
        if not self.stream_url.strip():
            raise InvalidSegmentRecorderConfig("stream url must not be blank")

    def build_command(self) -> list[str]:
        """Return an ffmpeg command using the segment muxer and fixed duration."""
        return [
            self.ffmpeg_path,
            "-y",
            "-i",
            self.stream_url,
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(self.segment_time_seconds),
            "-reset_timestamps",
            "1",
            str(self.output_dir / self.output_pattern),
        ]
