"""Factory for SQLAlchemy-backed segment processing."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.clock import Clock
from smhelper.core.ids import IdGenerator
from smhelper.infrastructure.media.ffmpeg.artifact_extractor import (
    FFmpegMediaArtifactExtractor,
)
from smhelper.infrastructure.media.ffmpeg.runner import (
    CommandRunner,
    SubprocessCommandRunner,
)
from smhelper.infrastructure.persistence.sqlalchemy.segment_processor import (
    SqlAlchemySegmentProcessor,
)
from smhelper.live.application.ports.media_artifacts import MediaArtifactExtractor
from smhelper.live.application.ports.question_generator import QuestionGenerator
from smhelper.live.application.ports.speech_to_text import SpeechToTextProvider
from smhelper.live.application.use_cases.process_segment import ProcessSegmentUseCase


def build_sqlalchemy_segment_processor(
    *,
    session_factory: sessionmaker[Session],
    speech_to_text: SpeechToTextProvider,
    question_generator: QuestionGenerator,
    ids: IdGenerator,
    clock: Clock,
    ffmpeg_path: str = "ffmpeg",
    command_runner: CommandRunner | None = None,
    media_artifacts: MediaArtifactExtractor | None = None,
) -> SqlAlchemySegmentProcessor:
    """Build the default SQLAlchemy segment processor from existing adapters."""
    resolved_media_artifacts = media_artifacts or FFmpegMediaArtifactExtractor(
        ffmpeg_path=ffmpeg_path,
        command_runner=command_runner or SubprocessCommandRunner(),
    )
    return SqlAlchemySegmentProcessor(
        session_factory=session_factory,
        ids=ids,
        clock=clock,
        processor=ProcessSegmentUseCase(
            media_artifacts=resolved_media_artifacts,
            speech_to_text=speech_to_text,
            question_generator=question_generator,
            ids=ids,
            clock=clock,
        ),
    )
