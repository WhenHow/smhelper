"""Port for extracting media artifacts from a completed segment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MediaArtifactRequest:
    """Request to generate first frame, last frame and audio artifacts."""

    video_path: Path
    artifact_dir: Path
    artifact_stem: str


@dataclass(frozen=True, slots=True)
class SegmentMediaArtifacts:
    """Media artifacts produced from one completed video segment."""

    first_frame_path: Path
    last_frame_path: Path
    audio_path: Path


class MediaArtifactExtractor(Protocol):
    """Extracts first/last frames and audio from a completed video segment."""

    def extract(self, request: MediaArtifactRequest) -> SegmentMediaArtifacts:
        """Generate segment artifacts and return their paths."""
