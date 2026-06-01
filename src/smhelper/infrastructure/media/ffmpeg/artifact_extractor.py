"""ffmpeg implementation of the media artifact extraction port."""

from __future__ import annotations

from dataclasses import dataclass

from smhelper.infrastructure.media.ffmpeg.audio import build_extract_audio_command
from smhelper.infrastructure.media.ffmpeg.runner import CommandRunner
from smhelper.infrastructure.media.ffmpeg.screenshots import (
    build_first_frame_command,
    build_last_frame_command,
)
from smhelper.live.application.ports.media_artifacts import (
    MediaArtifactRequest,
    SegmentMediaArtifacts,
)


@dataclass(frozen=True, slots=True)
class FFmpegMediaArtifactExtractor:
    """Extract first frame, last frame and audio using ffmpeg commands."""

    ffmpeg_path: str
    command_runner: CommandRunner

    def extract(self, request: MediaArtifactRequest) -> SegmentMediaArtifacts:
        """Generate media artifacts and return their paths."""
        artifacts = SegmentMediaArtifacts(
            first_frame_path=request.artifact_dir
            / f"{request.artifact_stem}_first.jpg",
            last_frame_path=request.artifact_dir / f"{request.artifact_stem}_last.jpg",
            audio_path=request.artifact_dir / f"{request.artifact_stem}.wav",
        )
        self.command_runner.run(
            build_first_frame_command(
                ffmpeg_path=self.ffmpeg_path,
                video_path=request.video_path,
                output_path=artifacts.first_frame_path,
            )
        )
        self.command_runner.run(
            build_last_frame_command(
                ffmpeg_path=self.ffmpeg_path,
                video_path=request.video_path,
                output_path=artifacts.last_frame_path,
            )
        )
        self.command_runner.run(
            build_extract_audio_command(
                ffmpeg_path=self.ffmpeg_path,
                video_path=request.video_path,
                output_path=artifacts.audio_path,
            )
        )
        return artifacts
