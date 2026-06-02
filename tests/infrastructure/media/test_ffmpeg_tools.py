from __future__ import annotations

from pathlib import Path

from smhelper.infrastructure.media.ffmpeg.audio import build_extract_audio_command
from smhelper.infrastructure.media.ffmpeg.runner import (
    SubprocessBackgroundProcessStarter,
)
from smhelper.infrastructure.media.ffmpeg.screenshots import (
    build_first_frame_command,
    build_last_frame_command,
)
from smhelper.infrastructure.media.ffmpeg.segment_recorder import (
    FFmpegSegmentRecorder,
)
from smhelper.infrastructure.media.ffmpeg.segment_scanner import SegmentScanner


def test_segment_recorder_builds_fixed_time_ffmpeg_segment_command(
    tmp_path: Path,
) -> None:
    recorder = FFmpegSegmentRecorder(
        ffmpeg_path="ffmpeg",
        stream_url="https://stream.example/live.flv",
        output_dir=tmp_path,
        segment_time_seconds=60,
    )

    command = recorder.build_command()

    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        "https://stream.example/live.flv",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        "60",
        "-reset_timestamps",
        "1",
        str(tmp_path / "segment_%05d.mp4"),
    ]


def test_background_process_starter_starts_command_without_waiting() -> None:
    calls: list[list[str]] = []

    def fake_popen(command: list[str]) -> object:
        calls.append(command)
        return object()

    SubprocessBackgroundProcessStarter(popen=fake_popen).start(["ffmpeg", "-version"])

    assert calls == [["ffmpeg", "-version"]]


def test_segment_scanner_treats_previous_file_as_complete_when_next_segment_exists(
    tmp_path: Path,
) -> None:
    first = tmp_path / "segment_00000.mp4"
    second = tmp_path / "segment_00001.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    completed = SegmentScanner(output_dir=tmp_path).completed_segments()

    assert completed == [first]


def test_segment_scanner_can_include_last_segment_when_recorder_stops(
    tmp_path: Path,
) -> None:
    first = tmp_path / "segment_00000.mp4"
    second = tmp_path / "segment_00001.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    completed = SegmentScanner(output_dir=tmp_path).completed_segments(
        include_last=True
    )

    assert completed == [first, second]


def test_media_artifact_commands_extract_first_last_frames_and_audio(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "segment_00000.mp4"
    first_frame = tmp_path / "segment_00000_first.jpg"
    last_frame = tmp_path / "segment_00000_last.jpg"
    audio_path = tmp_path / "segment_00000.wav"

    assert build_first_frame_command(
        ffmpeg_path="ffmpeg",
        video_path=video_path,
        output_path=first_frame,
    ) == ["ffmpeg", "-y", "-i", str(video_path), "-frames:v", "1", str(first_frame)]
    assert build_last_frame_command(
        ffmpeg_path="ffmpeg",
        video_path=video_path,
        output_path=last_frame,
    ) == [
        "ffmpeg",
        "-y",
        "-sseof",
        "-1",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(last_frame),
    ]
    assert build_extract_audio_command(
        ffmpeg_path="ffmpeg",
        video_path=video_path,
        output_path=audio_path,
    ) == [
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
        str(audio_path),
    ]
