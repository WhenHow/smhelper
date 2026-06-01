"""SQLAdmin views for candidate question review."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import select
from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse

from smhelper.infrastructure.persistence.sqlalchemy.live import CandidateQuestionRecord


class CandidateQuestionAdmin(ModelView, model=CandidateQuestionRecord):
    """Review, edit and approve generated candidate questions."""

    name_plural = "Candidate Questions"
    column_list: ClassVar[list[str]] = [
        "id",
        "live_task_id",
        "segment_id",
        "question",
        "risk_level",
        "status",
        "final_text",
        "reviewed_by",
        "reviewed_at",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "question", "final_text"]

    @action(
        name="approve",
        label="Approve",
        confirmation_message="Approve selected candidates for dispatch?",
    )
    async def approve_candidates(self, request: Request) -> RedirectResponse:
        """Mark selected candidates as approved after operator edits final text."""
        raw_pks = request.query_params.get("pks", "")
        candidate_ids = [
            candidate_id for candidate_id in raw_pks.split(",") if candidate_id
        ]
        if candidate_ids:
            with self.session_maker() as session:
                candidates = session.scalars(
                    select(CandidateQuestionRecord).where(
                        CandidateQuestionRecord.id.in_(candidate_ids)
                    )
                )
                for candidate in candidates:
                    if candidate.final_text and candidate.status == "pending_review":
                        candidate.status = "approved"
                session.commit()
        return RedirectResponse(
            request.headers.get("referer", "/admin/candidatequestion/list"),
            status_code=302,
        )
