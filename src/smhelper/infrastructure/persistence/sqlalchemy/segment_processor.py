"""SQLAlchemy-backed segment processing persistence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from smhelper.infrastructure.persistence.sqlalchemy.live import (
    CandidateQuestionRecord,
    LiveSegmentRecord,
    TranscriptRecord,
)
from smhelper.live.application.use_cases.process_segment import (
    ProcessSegmentInput,
    ProcessSegmentResult,
)


class SegmentProcessorUseCase(Protocol):
    """Application service that processes a completed live segment."""

    def process(self, request: ProcessSegmentInput) -> ProcessSegmentResult:
        """Process one segment and return persistence-ready artifacts."""


@dataclass(frozen=True, slots=True)
class SqlAlchemySegmentProcessor:
    """Load one segment, process it, and persist generated artifacts."""

    session_factory: sessionmaker[Session]
    processor: SegmentProcessorUseCase

    def process_segment(
        self,
        *,
        segment_id: str,
        product_context: str,
        task_context: str,
    ) -> str | None:
        """Process an uncompleted segment and return the candidate question id."""
        request = self._build_request(
            segment_id=segment_id,
            product_context=product_context,
            task_context=task_context,
        )
        if request is None:
            return None

        result = self.processor.process(request)
        return self._persist_result(segment_id=segment_id, result=result)

    def _build_request(
        self,
        *,
        segment_id: str,
        product_context: str,
        task_context: str,
    ) -> ProcessSegmentInput | None:
        with self.session_factory() as session:
            segment = session.get(LiveSegmentRecord, segment_id)
            if segment is None or segment.completed:
                return None
            return ProcessSegmentInput(
                live_task_id=segment.live_task_id,
                segment_id=segment.id,
                video_path=Path(segment.video_path),
                product_context=product_context,
                task_context=task_context,
            )

    def _persist_result(
        self,
        *,
        segment_id: str,
        result: ProcessSegmentResult,
    ) -> str | None:
        with self.session_factory() as session:
            segment = session.get(LiveSegmentRecord, segment_id)
            if segment is None or segment.completed:
                return None

            segment.first_frame_path = str(result.artifacts.first_frame_path)
            segment.last_frame_path = str(result.artifacts.last_frame_path)
            segment.audio_path = str(result.artifacts.audio_path)
            segment.completed = True
            segment.completed_at = result.transcript.transcribed_at
            session.add(
                TranscriptRecord(
                    id=result.transcript.id,
                    live_task_id=result.transcript.live_task_id,
                    segment_id=result.transcript.segment_id,
                    provider_name=result.transcript.provider_name,
                    text=result.transcript.text,
                    raw_response=result.transcript.raw_response,
                    status=result.transcript.status.value,
                    transcribed_at=result.transcript.transcribed_at,
                    failure_reason=result.transcript.failure_reason,
                )
            )
            session.add(
                CandidateQuestionRecord(
                    id=result.candidate.id,
                    live_task_id=result.candidate.live_task_id,
                    segment_id=result.candidate.segment_id,
                    question=result.candidate.question,
                    reason=result.candidate.reason,
                    risk_level=result.candidate.risk_level,
                    raw_response=result.candidate.raw_response,
                    status=result.candidate.status.value,
                    generated_at=result.candidate.generated_at,
                    final_text=result.candidate.final_text,
                    reviewed_by=result.candidate.reviewed_by,
                    reviewed_at=result.candidate.reviewed_at,
                    rejection_reason=result.candidate.rejection_reason,
                )
            )
            session.commit()
        return result.candidate.id
