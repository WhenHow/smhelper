"""Send attempt domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from smhelper.core.exceptions import SmHelperError


class InvalidSendAttempt(SmHelperError):
    """Raised when send-attempt audit data is incomplete."""


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

    @classmethod
    def failed(
        cls,
        *,
        id: str,
        dispatch_job_id: str,
        account_live_session_id: str,
        account_id: str,
        attempted_at: datetime,
        failure_reason: str,
    ) -> SendAttempt:
        """Create a first-phase failure audit record without scheduling retries."""
        normalized_failure_reason = failure_reason.strip()
        if not normalized_failure_reason:
            raise InvalidSendAttempt("send failure reason must not be blank")
        return cls(
            id=id,
            dispatch_job_id=dispatch_job_id,
            account_live_session_id=account_live_session_id,
            account_id=account_id,
            status=SendAttemptStatus.FAILED,
            success_detection=SuccessDetection.OPERATION_COMPLETED,
            attempted_at=attempted_at,
            failure_reason=normalized_failure_reason,
        )
