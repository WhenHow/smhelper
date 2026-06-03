"""SQLAlchemy-backed candidate review operations."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.clock import Clock
from smhelper.infrastructure.persistence.sqlalchemy.live import CandidateQuestionRecord


@dataclass(frozen=True, slots=True)
class SqlAlchemyCandidateReviewer:
    """Persist non-dispatch candidate review decisions."""

    session_factory: sessionmaker[Session]
    clock: Clock

    def reject(
        self,
        *,
        candidate_ids: list[str],
        reviewed_by: str,
    ) -> list[str]:
        """Reject pending candidates without creating dispatch jobs."""
        now = self.clock.now()
        rejected_ids: list[str] = []
        with self.session_factory() as session:
            candidates = session.scalars(
                select(CandidateQuestionRecord).where(
                    CandidateQuestionRecord.id.in_(candidate_ids)
                )
            ).all()
            for candidate in candidates:
                if candidate.status != "pending_review":
                    continue
                candidate.status = "rejected"
                candidate.final_text = None
                candidate.reviewed_by = reviewed_by
                candidate.reviewed_at = now
                candidate.rejection_reason = "operator_rejected"
                rejected_ids.append(candidate.id)
            session.commit()
        return rejected_ids

    def ignore(
        self,
        *,
        candidate_ids: list[str],
        reviewed_by: str,
    ) -> list[str]:
        """Ignore pending candidates without treating them as rejected."""
        now = self.clock.now()
        ignored_ids: list[str] = []
        with self.session_factory() as session:
            candidates = session.scalars(
                select(CandidateQuestionRecord).where(
                    CandidateQuestionRecord.id.in_(candidate_ids)
                )
            ).all()
            for candidate in candidates:
                if candidate.status != "pending_review":
                    continue
                candidate.status = "ignored"
                candidate.final_text = None
                candidate.reviewed_by = reviewed_by
                candidate.reviewed_at = now
                candidate.rejection_reason = None
                ignored_ids.append(candidate.id)
            session.commit()
        return ignored_ids
