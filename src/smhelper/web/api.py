"""Internal center API used by trusted worker nodes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    DispatchJobRecord,
    SendAttemptRecord,
)
from smhelper.live.domain.account_live_session import (
    RESTARTABLE_SESSION_STATUSES,
    AccountLiveSessionStatus,
)
from smhelper.live.domain.dispatch_job import DispatchJobStatus

router = APIRouter(prefix="/api")
RESTARTABLE_SESSION_STATUS_VALUES = {
    status.value for status in RESTARTABLE_SESSION_STATUSES
}
TERMINAL_SESSION_STATUS_VALUES = {
    AccountLiveSessionStatus.CLOSED.value,
    AccountLiveSessionStatus.FAILED.value,
    AccountLiveSessionStatus.LOST.value,
}


class AccountSessionRestarter(Protocol):
    """Center-side service that can rebuild an abnormal account session."""

    def restart_session(self, *, session_id: str) -> list[str]:
        """Try to rebuild a terminal abnormal session."""


class SessionStatusReport(BaseModel):
    """Worker-reported account live session status."""

    status: AccountLiveSessionStatus
    failure_reason: str | None = None


class SendResultReport(BaseModel):
    """Worker-reported result for one send dispatch job."""

    dispatch_job_id: str
    session_id: str
    account_id: str
    status: Literal["success", "failed"]
    failure_reason: str | None = None


@router.get("/accounts/{platform}/{account_id}/storage-state")
def get_account_storage_state(
    *,
    request: Request,
    platform: str,
    account_id: str,
) -> FileResponse:
    """Return the stored browser storage-state file for a valid account."""
    with Session(request.app.state.engine) as session:
        auth_state = session.get(
            AccountAuthStateRecord,
            {"account_id": account_id, "platform": platform},
        )

    if auth_state is None or auth_state.status != "valid":
        raise HTTPException(status_code=404, detail="storage state not found")
    storage_state_path = Path(auth_state.storage_state_path)
    if not storage_state_path.exists():
        raise HTTPException(status_code=404, detail="storage state file not found")
    return FileResponse(storage_state_path, media_type="application/json")


@router.post("/live/sessions/{session_id}/status")
def report_session_status(
    *,
    request: Request,
    session_id: str,
    report: SessionStatusReport,
) -> dict[str, str]:
    """Persist worker-reported session status."""
    now = _now(request)
    with Session(request.app.state.engine) as db_session:
        session_record = db_session.get(AccountLiveSessionRecord, session_id)
        if session_record is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session_record.status in TERMINAL_SESSION_STATUS_VALUES:
            return {"status": "ignored"}

        reported_status = report.status.value
        session_record.status = reported_status
        session_record.failure_reason = report.failure_reason
        session_record.last_heartbeat_at = now
        session_record.active_slot_key = AccountLiveSessionRecord.build_active_slot_key(
            live_task_id=session_record.live_task_id,
            account_id=session_record.account_id,
            status=reported_status,
        )
        if session_record.active_slot_key is None:
            session_record.closed_at = now
            session_record.send_started_at = None
            _fail_running_dispatch_jobs_for_terminal_session(
                db_session=db_session,
                session_record=session_record,
                now=now,
                failure_reason=report.failure_reason or f"session_{reported_status}",
            )
        db_session.commit()

    _restart_session_if_needed(
        request=request,
        session_id=session_id,
        status=reported_status,
    )
    return {"status": "ok"}


@router.post("/live/send-results")
def report_send_result(
    *,
    request: Request,
    report: SendResultReport,
) -> dict[str, str]:
    """Persist worker-reported send result and update related records."""
    now = _now(request)
    send_cooldown_seconds = int(getattr(request.app.state, "send_cooldown_seconds", 0))
    with Session(request.app.state.engine) as db_session:
        dispatch_job = db_session.get(DispatchJobRecord, report.dispatch_job_id)
        session_record = db_session.get(AccountLiveSessionRecord, report.session_id)
        account_record = db_session.get(PlatformAccountRecord, report.account_id)
        if dispatch_job is None:
            raise HTTPException(status_code=404, detail="dispatch job not found")
        if session_record is None:
            raise HTTPException(status_code=404, detail="session not found")
        if (
            dispatch_job.account_live_session_id != report.session_id
            or dispatch_job.account_id != report.account_id
            or session_record.account_id != dispatch_job.account_id
            or session_record.live_task_id != dispatch_job.live_task_id
        ):
            raise HTTPException(
                status_code=409,
                detail="send result does not match dispatch job",
            )
        if session_record.status in TERMINAL_SESSION_STATUS_VALUES:
            return {"status": "ignored"}
        if dispatch_job.status != DispatchJobStatus.RUNNING.value:
            return {"status": "ignored"}
        if session_record.status != AccountLiveSessionStatus.SENDING.value:
            return {"status": "ignored"}

        normalized_status = report.status
        db_session.add(
            SendAttemptRecord(
                id=f"attempt-{uuid4().hex}",
                dispatch_job_id=report.dispatch_job_id,
                account_live_session_id=report.session_id,
                account_id=report.account_id,
                status=normalized_status,
                success_detection="operation_completed",
                attempted_at=now,
                failure_reason=report.failure_reason,
            )
        )
        dispatch_job.status = normalized_status
        dispatch_job.finished_at = now
        dispatch_job.failure_reason = report.failure_reason
        session_record.status = "waiting"
        session_record.send_started_at = None
        if normalized_status == "success" and account_record is not None:
            session_record.last_send_at = now
            account_record.sends_today += 1
            cooldown_until = now + timedelta(seconds=send_cooldown_seconds)
            account_record.cooldown_until = cooldown_until
            session_record.cooldown_until = cooldown_until
        session_record.active_slot_key = AccountLiveSessionRecord.build_active_slot_key(
            live_task_id=session_record.live_task_id,
            account_id=session_record.account_id,
            status=session_record.status,
        )
        db_session.commit()

    return {"status": "ok"}


def _now(request: Request) -> datetime:
    clock = getattr(request.app.state, "clock", None)
    if clock is not None:
        return clock.now()
    return datetime.now(tz=UTC)


def _fail_running_dispatch_jobs_for_terminal_session(
    *,
    db_session: Session,
    session_record: AccountLiveSessionRecord,
    now: datetime,
    failure_reason: str,
) -> None:
    running_jobs = db_session.scalars(
        select(DispatchJobRecord).where(
            DispatchJobRecord.account_live_session_id == session_record.id,
            DispatchJobRecord.status == DispatchJobStatus.RUNNING.value,
        )
    ).all()
    for dispatch_job in running_jobs:
        db_session.add(
            SendAttemptRecord(
                id=f"attempt-{uuid4().hex}",
                dispatch_job_id=dispatch_job.id,
                account_live_session_id=session_record.id,
                account_id=dispatch_job.account_id,
                status="failed",
                success_detection="operation_completed",
                attempted_at=now,
                failure_reason=failure_reason,
            )
        )
        dispatch_job.status = DispatchJobStatus.FAILED.value
        dispatch_job.finished_at = now
        dispatch_job.failure_reason = failure_reason


def _restart_session_if_needed(
    *,
    request: Request,
    session_id: str,
    status: str,
) -> None:
    if status not in RESTARTABLE_SESSION_STATUS_VALUES:
        return
    restarter = cast(
        AccountSessionRestarter | None,
        getattr(request.app.state, "account_session_restarter", None),
    )
    if restarter is None:
        return
    restarter.restart_session(session_id=session_id)
