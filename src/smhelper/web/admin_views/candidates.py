"""SQLAdmin views for candidate question review."""

from __future__ import annotations

from typing import ClassVar, Protocol

from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse

from smhelper.infrastructure.persistence.sqlalchemy.live import CandidateQuestionRecord


class CandidateDispatcher(Protocol):
    """Dispatch service used by the SQLAdmin approve action."""

    def approve_and_dispatch(
        self,
        *,
        candidate_ids: list[str],
        reviewed_by: str,
    ) -> list[str]:
        """Approve candidates and publish send jobs."""


class CandidateReviewer(Protocol):
    """Review service used by SQLAdmin non-dispatch actions."""

    def reject(
        self,
        *,
        candidate_ids: list[str],
        reviewed_by: str,
    ) -> list[str]:
        """Reject pending candidates."""

    def ignore(
        self,
        *,
        candidate_ids: list[str],
        reviewed_by: str,
    ) -> list[str]:
        """Ignore pending candidates."""


class CandidateQuestionAdmin(ModelView, model=CandidateQuestionRecord):
    """Review, edit and approve generated candidate questions."""

    candidate_dispatcher: ClassVar[CandidateDispatcher | None] = None
    candidate_reviewer: ClassVar[CandidateReviewer | None] = None
    name_plural = "Candidate Questions"
    column_list: ClassVar[list[str]] = [
        "id",
        "live_task_id",
        "segment_id",
        "question",
        "reason",
        "risk_level",
        "status",
        "final_text",
        "reviewed_by",
        "reviewed_at",
        "rejection_reason",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "question", "final_text"]

    @action(
        name="approve",
        label="Approve",
        confirmation_message="Approve selected candidates for dispatch?",
    )
    async def approve_candidates(self, request: Request) -> RedirectResponse:
        """Approve selected candidates and dispatch send jobs."""
        raw_pks = request.query_params.get("pks", "")
        candidate_ids = [
            candidate_id for candidate_id in raw_pks.split(",") if candidate_id
        ]
        if candidate_ids:
            reviewed_by = str(request.session.get("admin_user", "admin"))
            if self.candidate_dispatcher is None:
                raise RuntimeError("candidate dispatcher is not configured")
            self.candidate_dispatcher.approve_and_dispatch(
                candidate_ids=candidate_ids,
                reviewed_by=reviewed_by,
            )
        return RedirectResponse(
            request.headers.get("referer", "/admin/candidatequestion/list"),
            status_code=302,
        )

    @action(
        name="reject",
        label="Reject",
        confirmation_message="Reject selected candidates?",
    )
    async def reject_candidates(self, request: Request) -> RedirectResponse:
        """Reject selected pending candidates without dispatching send jobs."""
        raw_pks = request.query_params.get("pks", "")
        candidate_ids = [
            candidate_id for candidate_id in raw_pks.split(",") if candidate_id
        ]
        if candidate_ids:
            reviewed_by = str(request.session.get("admin_user", "admin"))
            if self.candidate_reviewer is None:
                raise RuntimeError("candidate reviewer is not configured")
            self.candidate_reviewer.reject(
                candidate_ids=candidate_ids,
                reviewed_by=reviewed_by,
            )
        return RedirectResponse(
            request.headers.get("referer", "/admin/candidatequestion/list"),
            status_code=302,
        )

    @action(
        name="ignore",
        label="Ignore",
        confirmation_message="Ignore selected candidates?",
    )
    async def ignore_candidates(self, request: Request) -> RedirectResponse:
        """Ignore selected pending candidates without dispatching send jobs."""
        raw_pks = request.query_params.get("pks", "")
        candidate_ids = [
            candidate_id for candidate_id in raw_pks.split(",") if candidate_id
        ]
        if candidate_ids:
            reviewed_by = str(request.session.get("admin_user", "admin"))
            if self.candidate_reviewer is None:
                raise RuntimeError("candidate reviewer is not configured")
            self.candidate_reviewer.ignore(
                candidate_ids=candidate_ids,
                reviewed_by=reviewed_by,
            )
        return RedirectResponse(
            request.headers.get("referer", "/admin/candidatequestion/list"),
            status_code=302,
        )
