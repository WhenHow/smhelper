"""Process one completed segment into transcript and candidate question."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smhelper.core.clock import Clock
from smhelper.core.ids import IdGenerator
from smhelper.live.application.ports.media_artifacts import (
    MediaArtifactExtractor,
    MediaArtifactRequest,
    SegmentMediaArtifacts,
)
from smhelper.live.application.ports.question_generator import (
    QuestionGenerationPrompt,
    QuestionGenerator,
)
from smhelper.live.application.ports.speech_to_text import (
    SpeechToTextProvider,
    SpeechToTextRequest,
)
from smhelper.live.domain.candidate_question import (
    CandidateQuestion,
    CandidateQuestionStatus,
)
from smhelper.live.domain.transcript import Transcript, TranscriptStatus


@dataclass(frozen=True, slots=True)
class ProcessSegmentInput:
    """Inputs required to process one completed video segment."""

    live_task_id: str
    segment_id: str
    video_path: Path
    product_context: str
    task_context: str


@dataclass(frozen=True, slots=True)
class ProcessSegmentResult:
    """Artifacts produced by processing one completed segment."""

    artifacts: SegmentMediaArtifacts
    transcript: Transcript
    candidate: CandidateQuestion


@dataclass(frozen=True, slots=True)
class ProcessSegmentUseCase:
    """Run media extraction, ASR and LLM generation for one segment."""

    media_artifacts: MediaArtifactExtractor
    speech_to_text: SpeechToTextProvider
    question_generator: QuestionGenerator
    ids: IdGenerator
    clock: Clock

    def process(self, request: ProcessSegmentInput) -> ProcessSegmentResult:
        """Process a completed segment and return persistence-ready domain objects."""
        now = self.clock.now()
        artifacts = self.media_artifacts.extract(
            MediaArtifactRequest(
                video_path=request.video_path,
                artifact_dir=request.video_path.parent,
                artifact_stem=request.video_path.stem,
            )
        )
        transcription = self.speech_to_text.transcribe(
            SpeechToTextRequest(audio_path=artifacts.audio_path)
        )
        transcript = Transcript(
            id=self.ids.new_id("transcript"),
            live_task_id=request.live_task_id,
            segment_id=request.segment_id,
            text=transcription.text,
            provider_name=transcription.provider_name,
            raw_response=transcription.raw_response,
            status=TranscriptStatus.SUCCESS,
            transcribed_at=now,
        )
        question = self.question_generator.generate(
            QuestionGenerationPrompt(
                product_context=request.product_context,
                recent_transcript=transcript.text,
                task_context=request.task_context,
            )
        )
        candidate = CandidateQuestion(
            id=self.ids.new_id("candidate"),
            live_task_id=request.live_task_id,
            segment_id=request.segment_id,
            question=question.question,
            reason=question.reason,
            risk_level=question.risk_level,
            raw_response=question.raw_response,
            status=CandidateQuestionStatus.PENDING_REVIEW,
            generated_at=now,
        )
        return ProcessSegmentResult(
            artifacts=artifacts,
            transcript=transcript,
            candidate=candidate,
        )
