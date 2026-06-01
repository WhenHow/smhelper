"""Segment file completion detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SegmentScanner:
    """Detects completed ffmpeg segment files from an output directory."""

    output_dir: Path
    pattern: str = "segment_*.mp4"

    def completed_segments(self, *, include_last: bool = False) -> list[Path]:
        """Return files considered complete.

        During normal recording, a segment is treated as complete only after the
        next segment appears. On recorder stop, the caller can include the last
        segment for final processing.
        """
        segments = sorted(self.output_dir.glob(self.pattern))
        if include_last:
            return segments
        return segments[:-1]
