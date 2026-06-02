"""SQLAlchemy-backed live-task shutdown orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.clock import Clock
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    DispatchJobRecord,
    SendAttemptRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import CloseSessionPayload
from smhelper.live.domain.account_live_session import (
    ACTIVE_SESSION_STATUSES,
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.live.domain.policies.shutdown_policy import (
    CloseAction,
    LiveTaskShutdownPolicy,
)
from smhelper.live.domain.dispatch_job import DispatchJobStatus


class CloseSessionTaskPublisher(Protocol):
    """Publisher capable of asking browser nodes to close live-room sessions."""

    def close_session(
        self,
        *,
        queue_name: str,
        payload: CloseSessionPayload,
    ) -> None:
        """Publish one close-session task."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyLiveTaskShutdownCoordinator:
    """Close or mark account sessions when the center observes a live task ending."""

    session_factory: sessionmaker[Session]
    clock: Clock
    shutdown_policy: LiveTaskShutdownPolicy
    browser_task_publisher: CloseSessionTaskPublisher

    def close_active_sessions(self, *, live_task_id: str) -> list[str]:
        """Apply shutdown decisions for active sessions of one live task."""
        now = self.clock.now()
        published_closes: list[tuple[str, CloseSessionPayload]] = []
        handled_session_ids: list[str] = []

        with self.session_factory() as session:
            session_records = self._load_active_sessions(
                session=session,
                live_task_id=live_task_id,
            )
            worker_records = self._load_workers_by_id(session=session)
            records_by_id = {record.id: record for record in session_records}
            decisions = self.shutdown_policy.plan_closures(
                sessions=[self._to_domain(record) for record in session_records],
                now=now,
            )

            for decision in decisions:
                record = records_by_id[decision.session_id]
                if decision.action is CloseAction.WAIT_FOR_SENDING:
                    continue

                if decision.action is CloseAction.FORCE_CLOSE:
                    self._mark_lost(
                        record=record,
                        reason=decision.reason,
                        closed_at=now,
                    )
                    self._fail_running_dispatch_jobs(
                        session=session,
                        record=record,
                        reason=decision.reason,
                        failed_at=now,
                    )
                    handled_session_ids.append(record.id)
                    continue

                worker = worker_records.get(decision.node_id)
                if worker is None:
                    self._mark_lost(
                        record=record,
                        reason="worker_not_found",
                        closed_at=now,
                    )
                    self._fail_running_dispatch_jobs(
                        session=session,
                        record=record,
                        reason="worker_not_found",
                        failed_at=now,
                    )
                    handled_session_ids.append(record.id)
                    continue

                record.status = AccountLiveSessionStatus.CLOSING.value
                record.failure_reason = decision.reason
                record.active_slot_key = AccountLiveSessionRecord.build_active_slot_key(
                    live_task_id=record.live_task_id,
                    account_id=record.account_id,
                    status=record.status,
                )
                published_closes.append(
                    (
                        worker.queue_name,
                        CloseSessionPayload(
                            session_id=record.id,
                            reason=decision.reason,
                        ),
                    )
                )
                handled_session_ids.append(record.id)

            session.commit()

        for queue_name, payload in published_closes:
            self.browser_task_publisher.close_session(
                queue_name=queue_name,
                payload=payload,
            )
        return handled_session_ids

    @staticmethod
    def _load_active_sessions(
        *,
        session: Session,
        live_task_id: str,
    ) -> list[AccountLiveSessionRecord]:
        active_statuses = [status.value for status in ACTIVE_SESSION_STATUSES]
        return list(
            session.scalars(
                select(AccountLiveSessionRecord).where(
                    AccountLiveSessionRecord.live_task_id == live_task_id,
                    AccountLiveSessionRecord.status.in_(active_statuses),
                )
            ).all()
        )

    @staticmethod
    def _load_workers_by_id(*, session: Session) -> dict[str, WorkerNodeRecord]:
        return {
            worker.id: worker
            for worker in session.scalars(select(WorkerNodeRecord)).all()
        }

    @staticmethod
    def _mark_lost(
        *,
        record: AccountLiveSessionRecord,
        reason: str,
        closed_at: datetime,
    ) -> None:
        record.status = AccountLiveSessionStatus.LOST.value
        record.failure_reason = reason
        record.closed_at = closed_at
        record.active_slot_key = AccountLiveSessionRecord.build_active_slot_key(
            live_task_id=record.live_task_id,
            account_id=record.account_id,
            status=record.status,
        )

    @staticmethod
    def _fail_running_dispatch_jobs(
        *,
        session: Session,
        record: AccountLiveSessionRecord,
        reason: str,
        failed_at: datetime,
    ) -> None:
        running_jobs = session.scalars(
            select(DispatchJobRecord).where(
                DispatchJobRecord.account_live_session_id == record.id,
                DispatchJobRecord.status == DispatchJobStatus.RUNNING.value,
            )
        ).all()
        for job in running_jobs:
            session.add(
                SendAttemptRecord(
                    id=f"attempt-{uuid4().hex}",
                    dispatch_job_id=job.id,
                    account_live_session_id=record.id,
                    account_id=job.account_id,
                    status="failed",
                    success_detection="operation_completed",
                    attempted_at=failed_at,
                    failure_reason=reason,
                )
            )
            job.status = DispatchJobStatus.FAILED.value
            job.finished_at = failed_at
            job.failure_reason = reason

    @staticmethod
    def _to_domain(record: AccountLiveSessionRecord) -> AccountLiveSession:
        return AccountLiveSession(
            id=record.id,
            live_task_id=record.live_task_id,
            platform=record.platform,
            room_url=record.room_url,
            account_id=record.account_id,
            node_id=record.node_id,
            status=AccountLiveSessionStatus(record.status),
            opened_at=_as_aware_utc(record.opened_at),
            last_heartbeat_at=_as_aware_utc(record.last_heartbeat_at),
            last_send_at=_as_aware_utc(record.last_send_at),
            failure_reason=record.failure_reason,
            closed_at=_as_aware_utc(record.closed_at),
            restart_count=record.restart_count,
            cooldown_until=_as_aware_utc(record.cooldown_until),
            send_started_at=_as_aware_utc(record.send_started_at),
        )


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
