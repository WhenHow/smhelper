from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.live.application.ports.media_artifacts import (
    MediaArtifactRequest,
    SegmentMediaArtifacts,
)
from smhelper.live.application.ports.question_generator import (
    GeneratedQuestionDraft,
    QuestionGenerationPrompt,
)
from smhelper.live.application.ports.speech_to_text import (
    SpeechToTextRequest,
    TranscriptionResult,
)
from smhelper.live.application.use_cases.process_segment import (
    ProcessSegmentInput,
    ProcessSegmentUseCase,
)
from smhelper.live.domain.candidate_question import CandidateQuestionStatus


@dataclass
class FakeMediaArtifactExtractor:
    artifacts: SegmentMediaArtifacts
    requests: list[MediaArtifactRequest] = field(default_factory=list)

    def extract(self, request: MediaArtifactRequest) -> SegmentMediaArtifacts:
        self.requests.append(request)
        return self.artifacts


@dataclass
class FakeSpeechToText:
    requests: list[SpeechToTextRequest] = field(default_factory=list)

    def transcribe(self, request: SpeechToTextRequest) -> TranscriptionResult:
        self.requests.append(request)
        return TranscriptionResult(
            text="The host mentioned oily skin and texture.",
            provider_name="vendor-a",
            raw_response='{"text":"ok"}',
        )


@dataclass
class FakeQuestionGenerator:
    prompts: list[QuestionGenerationPrompt] = field(default_factory=list)

    def generate(self, prompt: QuestionGenerationPrompt) -> GeneratedQuestionDraft:
        self.prompts.append(prompt)
        return GeneratedQuestionDraft(
            question="Is this suitable for oily skin?",
            reason="The transcript mentions oily skin.",
            risk_level="low",
            raw_response='{"question":"Is this suitable for oily skin?"}',
        )


def test_process_segment_extracts_artifacts_transcribes_audio_and_generates_candidate(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 1, 12, 1, tzinfo=UTC)
    video_path = tmp_path / "segment_00001.mp4"
    artifacts = SegmentMediaArtifacts(
        first_frame_path=tmp_path / "segment_00001_first.jpg",
        last_frame_path=tmp_path / "segment_00001_last.jpg",
        audio_path=tmp_path / "segment_00001.wav",
    )
    media = FakeMediaArtifactExtractor(artifacts=artifacts)
    speech_to_text = FakeSpeechToText()
    question_generator = FakeQuestionGenerator()

    result = ProcessSegmentUseCase(
        media_artifacts=media,
        speech_to_text=speech_to_text,
        question_generator=question_generator,
        ids=SequenceIdGenerator(["transcript-1", "candidate-1"]),
        clock=FixedClock(now),
    ).process(
        ProcessSegmentInput(
            live_task_id="live-1",
            segment_id="segment-1",
            video_path=video_path,
            product_context="Face cream for oily skin.",
            task_context="Ask only product-related questions.",
        )
    )

    assert media.requests == [
        MediaArtifactRequest(
            video_path=video_path,
            artifact_dir=tmp_path,
            artifact_stem="segment_00001",
        )
    ]
    assert speech_to_text.requests == [
        SpeechToTextRequest(audio_path=artifacts.audio_path)
    ]
    assert question_generator.prompts == [
        QuestionGenerationPrompt(
            product_context="Face cream for oily skin.",
            recent_transcript="The host mentioned oily skin and texture.",
            task_context="Ask only product-related questions.",
        )
    ]
    assert result.artifacts == artifacts
    assert result.transcript.id == "transcript-1"
    assert result.transcript.text == "The host mentioned oily skin and texture."
    assert result.candidate.id == "candidate-1"
    assert result.candidate.status is CandidateQuestionStatus.PENDING_REVIEW
    assert result.candidate.question == "Is this suitable for oily skin?"
