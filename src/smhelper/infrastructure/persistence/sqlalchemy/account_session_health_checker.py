"""SQLAlchemy-backed scheduling for account live-session health checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import CheckSessionPayload
from smhelper.live.domain.account_live_session import AccountLiveSessionStatus

CHECKABLE_SESSION_STATUS_VALUES = frozenset(
    {
        AccountLiveSessionStatus.WAITING.value,
        AccountLiveSessionStatus.SENDING.value,
    }
)


class BrowserSessionHealthPublisher(Protocol):
    """Publisher capable of asking worker nodes to check live-room sessions."""

    def check_session(
        self,
        *,
        queue_name: str,
        payload: CheckSessionPayload,
    ) -> None:
        """Publish one browser-session health check."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyAccountSessionHealthChecker:
    """Publish worker-side health checks for open account live sessions."""

    session_factory: sessionmaker[Session]
    browser_task_publisher: BrowserSessionHealthPublisher

    def check_live_task_sessions(self, *, live_task_id: str) -> list[str]:
        """Publish health checks for currently open sessions of one live task."""
        with self.session_factory() as session:
            worker_records = {
                worker.id: worker
                for worker in session.scalars(select(WorkerNodeRecord)).all()
                if worker.online
            }
            session_records = session.scalars(
                select(AccountLiveSessionRecord)
                .where(
                    AccountLiveSessionRecord.live_task_id == live_task_id,
                    AccountLiveSessionRecord.status.in_(
                        CHECKABLE_SESSION_STATUS_VALUES
                    ),
                )
                .order_by(AccountLiveSessionRecord.id)
            ).all()

        checked_session_ids: list[str] = []
        for session_record in session_records:
            worker = worker_records.get(session_record.node_id)
            if worker is None:
                continue
            self.browser_task_publisher.check_session(
                queue_name=worker.queue_name,
                payload=CheckSessionPayload(session_id=session_record.id),
            )
            checked_session_ids.append(session_record.id)
        return checked_session_ids
