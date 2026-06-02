from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    CandidateQuestionRecord,
    LiveSegmentRecord,
    TranscriptRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_session_factory,
)
from smhelper.infrastructure.persistence.sqlalchemy.segment_processor import (
    SqlAlchemySegmentProcessor,
)
from smhelper.live.application.ports.media_artifacts import SegmentMediaArtifacts
from smhelper.live.application.use_cases.process_segment import (
    ProcessSegmentInput,
    ProcessSegmentResult,
)
from smhelper.live.domain.candidate_question import (
    CandidateQuestion,
    CandidateQuestionStatus,
)
from smhelper.live.domain.transcript import Transcript, TranscriptStatus


@dataclass
class FakeProcessSegmentUseCase:
    result: ProcessSegmentResult
    requests: list[ProcessSegmentInput] = field(default_factory=list)

    def process(self, request: ProcessSegmentInput) -> ProcessSegmentResult:
        self.requests.append(request)
        return self.result


@dataclass
class FailingProcessSegmentUseCase:
    error: Exception
    requests: list[ProcessSegmentInput] = field(default_factory=list)

    def process(self, request: ProcessSegmentInput) -> ProcessSegmentResult:
        self.requests.append(request)
        raise self.error


def test_segment_processor_persists_artifacts_transcript_and_candidate(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    created_at = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    processed_at = datetime(2026, 6, 2, 10, 1, tzinfo=UTC)
    video_path = tmp_path / "segment_00001.mp4"
    artifacts = SegmentMediaArtifacts(
        first_frame_path=tmp_path / "segment_00001_first.jpg",
        last_frame_path=tmp_path / "segment_00001_last.jpg",
        audio_path=tmp_path / "segment_00001.wav",
    )
    processor = FakeProcessSegmentUseCase(
        result=ProcessSegmentResult(
            artifacts=artifacts,
            transcript=Transcript(
                id="transcript-1",
                live_task_id="live-1",
                segment_id="segment-1",
                text="The host mentioned oily skin.",
                provider_name="vendor-a",
                raw_response='{"text":"ok"}',
                status=TranscriptStatus.SUCCESS,
                transcribed_at=processed_at,
            ),
            candidate=CandidateQuestion(
                id="candidate-1",
                live_task_id="live-1",
                segment_id="segment-1",
                question="Is this suitable for oily skin?",
                reason="The transcript mentions oily skin.",
                risk_level="low",
                raw_response='{"question":"Is this suitable for oily skin?"}',
                status=CandidateQuestionStatus.PENDING_REVIEW,
                generated_at=processed_at,
            ),
        )
    )
    with Session(engine) as session:
        session.add(
            LiveSegmentRecord(
                id="segment-1",
                live_task_id="live-1",
                sequence=1,
                video_path=str(video_path),
                completed=False,
                created_at=created_at,
            )
        )
        session.commit()

    candidate_id = SqlAlchemySegmentProcessor(
        session_factory=session_factory,
        processor=processor,
    ).process_segment(
        segment_id="segment-1",
        product_context="Face cream for oily skin.",
        task_context="Ask only product-related questions.",
    )

    assert candidate_id == "candidate-1"
    assert processor.requests == [
        ProcessSegmentInput(
            live_task_id="live-1",
            segment_id="segment-1",
            video_path=video_path,
            product_context="Face cream for oily skin.",
            task_context="Ask only product-related questions.",
        )
    ]
    with Session(engine) as session:
        segment = session.get(LiveSegmentRecord, "segment-1")
        transcript = session.get(TranscriptRecord, "transcript-1")
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        assert segment is not None
        assert segment.first_frame_path == str(artifacts.first_frame_path)
        assert segment.last_frame_path == str(artifacts.last_frame_path)
        assert segment.audio_path == str(artifacts.audio_path)
        assert segment.completed is True
        assert segment.completed_at == processed_at.replace(tzinfo=None)
        assert transcript is not None
        assert transcript.text == "The host mentioned oily skin."
        assert transcript.provider_name == "vendor-a"
        assert transcript.status == "success"
        assert candidate is not None
        assert candidate.question == "Is this suitable for oily skin?"
        assert candidate.status == "pending_review"
        assert candidate.generated_at == processed_at.replace(tzinfo=None)
    engine.dispose()


def test_segment_processor_skips_missing_or_already_completed_segment(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    processed_at = datetime(2026, 6, 2, 10, 1, tzinfo=UTC)
    processor = FakeProcessSegmentUseCase(
        result=ProcessSegmentResult(
            artifacts=SegmentMediaArtifacts(
                first_frame_path=tmp_path / "first.jpg",
                last_frame_path=tmp_path / "last.jpg",
                audio_path=tmp_path / "audio.wav",
            ),
            transcript=Transcript(
                id="transcript-1",
                live_task_id="live-1",
                segment_id="segment-1",
                text="ok",
                provider_name="vendor-a",
                raw_response="{}",
                status=TranscriptStatus.SUCCESS,
                transcribed_at=processed_at,
            ),
            candidate=CandidateQuestion(
                id="candidate-1",
                live_task_id="live-1",
                segment_id="segment-1",
                question="Question?",
                reason="Reason.",
                risk_level="low",
                raw_response="{}",
                status=CandidateQuestionStatus.PENDING_REVIEW,
                generated_at=processed_at,
            ),
        )
    )
    with Session(engine) as session:
        session.add(
            LiveSegmentRecord(
                id="segment-1",
                live_task_id="live-1",
                sequence=1,
                video_path=str(tmp_path / "segment_00001.mp4"),
                completed=True,
                created_at=processed_at,
                completed_at=processed_at,
            )
        )
        session.commit()

    subject = SqlAlchemySegmentProcessor(
        session_factory=session_factory,
        processor=processor,
    )

    assert (
        subject.process_segment(
            segment_id="missing",
            product_context="Product.",
            task_context="Task.",
        )
        is None
    )
    assert (
        subject.process_segment(
            segment_id="segment-1",
            product_context="Product.",
            task_context="Task.",
        )
        is None
    )
    assert processor.requests == []
    engine.dispose()


def test_segment_processor_records_failed_transcript_when_processing_raises(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    created_at = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    failed_at = datetime(2026, 6, 2, 10, 1, tzinfo=UTC)
    video_path = tmp_path / "segment_00001.mp4"
    processor = FailingProcessSegmentUseCase(RuntimeError("asr provider timeout"))
    with Session(engine) as session:
        session.add(
            LiveSegmentRecord(
                id="segment-1",
                live_task_id="live-1",
                sequence=1,
                video_path=str(video_path),
                completed=False,
                created_at=created_at,
            )
        )
        session.commit()

    candidate_id = SqlAlchemySegmentProcessor(
        session_factory=session_factory,
        processor=processor,
        ids=SequenceIdGenerator(["transcript-failed"]),
        clock=FixedClock(failed_at),
    ).process_segment(
        segment_id="segment-1",
        product_context="Product.",
        task_context="Task.",
    )

    assert candidate_id is None
    assert processor.requests == [
        ProcessSegmentInput(
            live_task_id="live-1",
            segment_id="segment-1",
            video_path=video_path,
            product_context="Product.",
            task_context="Task.",
        )
    ]
    with Session(engine) as session:
        segment = session.get(LiveSegmentRecord, "segment-1")
        transcript = session.get(TranscriptRecord, "transcript-failed")
        candidates = session.query(CandidateQuestionRecord).all()
        assert segment is not None
        assert segment.completed is True
        assert segment.completed_at == failed_at.replace(tzinfo=None)
        assert transcript is not None
        assert transcript.live_task_id == "live-1"
        assert transcript.segment_id == "segment-1"
        assert transcript.status == "failed"
        assert transcript.provider_name == "segment_processor"
        assert transcript.text == ""
        assert transcript.raw_response == "{}"
        assert transcript.failure_reason == "asr provider timeout"
        assert candidates == []
    engine.dispose()
