"""Approve a candidate question and create a dispatch job."""

from __future__ import annotations

from dataclasses import dataclass

from smhelper.core.clock import Clock
from smhelper.core.ids import IdGenerator
from smhelper.live.domain.account_live_session import AccountLiveSession
from smhelper.live.domain.candidate_question import CandidateQuestion
from smhelper.live.domain.dispatch_job import DispatchJob
from smhelper.live.domain.policies.send_account_policy import SendAccountPolicy


@dataclass(frozen=True, slots=True)
class CandidateApprovalResult:
    """Result of approving a candidate and selecting a send session."""

    candidate: CandidateQuestion
    dispatch_job: DispatchJob


@dataclass(frozen=True, slots=True)
class ApproveCandidateQuestionUseCase:
    """Approve an operator-edited candidate and prepare one dispatch job."""

    clock: Clock
    ids: IdGenerator
    send_account_policy: SendAccountPolicy

    def approve(
        self,
        *,
        candidate: CandidateQuestion,
        final_text: str,
        reviewed_by: str,
        sessions: list[AccountLiveSession],
    ) -> CandidateApprovalResult:
        """Approve the candidate and create a pending dispatch job."""
        now = self.clock.now()
        approved = candidate.approve(
            final_text=final_text,
            reviewed_by=reviewed_by,
            reviewed_at=now,
        )
        selected_session = self.send_account_policy.select_session(
            sessions=sessions,
            now=now,
        )
        dispatch_job = DispatchJob.create(
            id=self.ids.new_id("job"),
            candidate_question_id=approved.id,
            live_task_id=approved.live_task_id,
            account_live_session_id=selected_session.id,
            account_id=selected_session.account_id,
            final_text=approved.final_text or "",
            created_at=now,
        )
        return CandidateApprovalResult(candidate=approved, dispatch_job=dispatch_job)
