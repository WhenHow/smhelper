from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.candidate_reviewer import (
    SqlAlchemyCandidateReviewer,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import CandidateQuestionRecord
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)


def test_candidate_reviewer_rejects_only_pending_candidates() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    generated_at = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    reviewed_at = datetime(2026, 6, 2, 10, 1, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(
            [
                CandidateQuestionRecord(
                    id="candidate-pending",
                    live_task_id="live-1",
                    segment_id="segment-1",
                    question="Unrelated question?",
                    reason="weak context",
                    risk_level="medium",
                    raw_response="{}",
                    status="pending_review",
                    final_text="Unrelated question?",
                    generated_at=generated_at,
                ),
                CandidateQuestionRecord(
                    id="candidate-approved",
                    live_task_id="live-1",
                    segment_id="segment-2",
                    question="Approved question?",
                    reason="good context",
                    risk_level="low",
                    raw_response="{}",
                    status="approved",
                    final_text="Approved question?",
                    generated_at=generated_at,
                ),
            ]
        )
        session.commit()

    rejected = SqlAlchemyCandidateReviewer(
        session_factory=session_factory,
        clock=FixedClock(reviewed_at),
    ).reject(
        candidate_ids=["candidate-pending", "candidate-approved"],
        reviewed_by="admin",
    )

    assert rejected == ["candidate-pending"]
    with Session(engine) as session:
        pending = session.get(CandidateQuestionRecord, "candidate-pending")
        approved = session.get(CandidateQuestionRecord, "candidate-approved")
        assert pending is not None
        assert pending.status == "rejected"
        assert pending.final_text is None
        assert pending.reviewed_by == "admin"
        assert pending.reviewed_at == reviewed_at.replace(tzinfo=None)
        assert pending.rejection_reason == "operator_rejected"
        assert approved is not None
        assert approved.status == "approved"
        assert approved.final_text == "Approved question?"
    engine.dispose()


def test_candidate_reviewer_ignores_only_pending_candidates() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    generated_at = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    reviewed_at = datetime(2026, 6, 2, 10, 1, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(
            [
                CandidateQuestionRecord(
                    id="candidate-pending",
                    live_task_id="live-1",
                    segment_id="segment-1",
                    question="Weak question?",
                    reason="weak context",
                    risk_level="medium",
                    raw_response="{}",
                    status="pending_review",
                    final_text="Weak question?",
                    generated_at=generated_at,
                    rejection_reason="old reason",
                ),
                CandidateQuestionRecord(
                    id="candidate-rejected",
                    live_task_id="live-1",
                    segment_id="segment-2",
                    question="Rejected question?",
                    reason="bad context",
                    risk_level="high",
                    raw_response="{}",
                    status="rejected",
                    final_text=None,
                    generated_at=generated_at,
                    rejection_reason="operator_rejected",
                ),
            ]
        )
        session.commit()

    ignored = SqlAlchemyCandidateReviewer(
        session_factory=session_factory,
        clock=FixedClock(reviewed_at),
    ).ignore(
        candidate_ids=["candidate-pending", "candidate-rejected"],
        reviewed_by="admin",
    )

    assert ignored == ["candidate-pending"]
    with Session(engine) as session:
        pending = session.get(CandidateQuestionRecord, "candidate-pending")
        rejected = session.get(CandidateQuestionRecord, "candidate-rejected")
        assert pending is not None
        assert pending.status == "ignored"
        assert pending.final_text is None
        assert pending.reviewed_by == "admin"
        assert pending.reviewed_at == reviewed_at.replace(tzinfo=None)
        assert pending.rejection_reason is None
        assert rejected is not None
        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "operator_rejected"
    engine.dispose()
