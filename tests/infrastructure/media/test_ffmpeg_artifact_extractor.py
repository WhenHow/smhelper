from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from smhelper.infrastructure.media.ffmpeg.artifact_extractor import (
    FFmpegMediaArtifactExtractor,
)
from smhelper.live.application.ports.media_artifacts import MediaArtifactRequest


@dataclass
class FakeCommandRunner:
    commands: list[list[str]] = field(default_factory=list)

    def run(self, command: list[str]) -> None:
        self.commands.append(command)


def test_ffmpeg_media_artifact_extractor_builds_and_runs_all_artifact_commands(
    tmp_path: Path,
) -> None:
    runner = FakeCommandRunner()
    video_path = tmp_path / "segment_00001.mp4"

    artifacts = FFmpegMediaArtifactExtractor(
        ffmpeg_path="ffmpeg",
        command_runner=runner,
    ).extract(
        MediaArtifactRequest(
            video_path=video_path,
            artifact_dir=tmp_path,
            artifact_stem="segment_00001",
        )
    )

    assert artifacts.first_frame_path == tmp_path / "segment_00001_first.jpg"
    assert artifacts.last_frame_path == tmp_path / "segment_00001_last.jpg"
    assert artifacts.audio_path == tmp_path / "segment_00001.wav"
    assert runner.commands == [
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(artifacts.first_frame_path),
        ],
        [
            "ffmpeg",
            "-y",
            "-sseof",
            "-1",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(artifacts.last_frame_path),
        ],
        [
            "ffmpeg",
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
            str(artifacts.audio_path),
        ],
    ]
