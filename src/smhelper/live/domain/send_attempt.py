"""Send attempt domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SendAttemptStatus(str, Enum):
    """Outcome of a worker-side send operation."""

    SUCCESS = "success"
    FAILED = "failed"


class SuccessDetection(str, Enum):
    """Strategy used to classify a send operation as successful."""

    OPERATION_COMPLETED = "operation_completed"


@dataclass(frozen=True, slots=True)
class SendAttempt:
    """Audit record for one send operation."""

    id: str
    dispatch_job_id: str
    account_live_session_id: str
    account_id: str
    status: SendAttemptStatus
    success_detection: SuccessDetection
    attempted_at: datetime
    failure_reason: str | None = None

    @classmethod
    def success(
        cls,
        *,
        id: str,
        dispatch_job_id: str,
        account_live_session_id: str,
        account_id: str,
        sent_at: datetime,
    ) -> SendAttempt:
        """Create a first-phase success record after browser operations finish."""
        return cls(
            id=id,
            dispatch_job_id=dispatch_job_id,
            account_live_session_id=account_live_session_id,
            account_id=account_id,
            status=SendAttemptStatus.SUCCESS,
            success_detection=SuccessDetection.OPERATION_COMPLETED,
            attempted_at=sent_at,
        )
