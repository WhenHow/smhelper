from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import create_engine

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.media.ffmpeg.artifact_extractor import (
    FFmpegMediaArtifactExtractor,
)
from smhelper.infrastructure.media.ffmpeg.runner import CommandRunner
from smhelper.infrastructure.persistence.sqlalchemy.segment_processor import (
    SqlAlchemySegmentProcessor,
)
from smhelper.infrastructure.persistence.sqlalchemy.segment_processor_factory import (
    build_sqlalchemy_segment_processor,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_session_factory,
)
from smhelper.live.application.ports.question_generator import (
    GeneratedQuestionDraft,
    QuestionGenerationPrompt,
)
from smhelper.live.application.ports.speech_to_text import (
    SpeechToTextRequest,
    TranscriptionResult,
)
from smhelper.live.application.use_cases.process_segment import ProcessSegmentUseCase


@dataclass
class FakeCommandRunner(CommandRunner):
    commands: list[list[str]]

    def run(self, command: list[str]) -> None:
        self.commands.append(command)


@dataclass
class FakeSpeechToText:
    def transcribe(self, request: SpeechToTextRequest) -> TranscriptionResult:
        return TranscriptionResult(
            text=f"transcribed {request.audio_path.name}",
            provider_name="vendor-a",
            raw_response="{}",
        )


@dataclass
class FakeQuestionGenerator:
    def generate(self, prompt: QuestionGenerationPrompt) -> GeneratedQuestionDraft:
        return GeneratedQuestionDraft(
            question=f"Question from {prompt.recent_transcript}?",
            reason="Reason.",
            risk_level="low",
            raw_response="{}",
        )


def test_build_sqlalchemy_segment_processor_wires_default_ffmpeg_artifacts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    clock = FixedClock(datetime(2026, 6, 2, 10, 0, tzinfo=UTC))
    ids = SequenceIdGenerator(["transcript-1", "candidate-1"])
    speech_to_text = FakeSpeechToText()
    question_generator = FakeQuestionGenerator()
    command_runner = FakeCommandRunner(commands=[])

    processor = build_sqlalchemy_segment_processor(
        session_factory=session_factory,
        speech_to_text=speech_to_text,
        question_generator=question_generator,
        ids=ids,
        clock=clock,
        ffmpeg_path="ffmpeg-custom",
        command_runner=command_runner,
    )

    assert isinstance(processor, SqlAlchemySegmentProcessor)
    assert isinstance(processor.processor, ProcessSegmentUseCase)
    assert processor.processor.speech_to_text is speech_to_text
    assert processor.processor.question_generator is question_generator
    assert processor.processor.ids is ids
    assert processor.processor.clock is clock
    assert isinstance(processor.processor.media_artifacts, FFmpegMediaArtifactExtractor)
    assert processor.processor.media_artifacts.ffmpeg_path == "ffmpeg-custom"
    assert processor.processor.media_artifacts.command_runner is command_runner
    engine.dispose()
