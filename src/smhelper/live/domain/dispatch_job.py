"""Dispatch job domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from smhelper.core.exceptions import SmHelperError


class InvalidDispatchJob(SmHelperError):
    """Raised when a dispatch job cannot be created."""


class DispatchJobStatus(str, Enum):
    """Execution status for sending an approved question."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DispatchJob:
    """A request for a worker node to send one approved question."""

    id: str
    candidate_question_id: str
    live_task_id: str
    account_live_session_id: str
    account_id: str
    final_text: str
    status: DispatchJobStatus
    created_at: datetime
    failure_reason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        id: str,
        candidate_question_id: str,
        live_task_id: str,
        account_live_session_id: str,
        account_id: str,
        final_text: str,
        created_at: datetime,
    ) -> DispatchJob:
        """Create a pending dispatch job from an approved question."""
        normalized_final_text = final_text.strip()
        if not normalized_final_text:
            raise InvalidDispatchJob("dispatch final text must not be blank")
        return cls(
            id=id,
            candidate_question_id=candidate_question_id,
            live_task_id=live_task_id,
            account_live_session_id=account_live_session_id,
            account_id=account_id,
            final_text=normalized_final_text,
            status=DispatchJobStatus.PENDING,
            created_at=created_at,
        )
