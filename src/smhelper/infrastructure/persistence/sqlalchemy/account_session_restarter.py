"""SQLAlchemy-backed account live-session restart orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.ids import IdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.live.application.use_cases.plan_account_entries import AccountEntryPlan
from smhelper.live.domain.account_live_session import (
    ACTIVE_SESSION_STATUSES,
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.workers.domain.rendezvous_hashing import (
    NoAvailableWorkerNode,
    RendezvousHashingNodeSelector,
)
from smhelper.workers.domain.worker_node import WorkerNode


class AccountEntryDispatcher(Protocol):
    """Dispatcher capable of persisting and publishing account entry plans."""

    def dispatch(self, plans: list[AccountEntryPlan]) -> list[str]:
        """Persist entry plans and publish worker-node tasks."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyAccountSessionRestarter:
    """Rebuild abnormal terminal account sessions within the configured limit."""

    session_factory: sessionmaker[Session]
    ids: IdGenerator
    dispatcher: AccountEntryDispatcher
    max_restarts: int = 2
    selector: RendezvousHashingNodeSelector = RendezvousHashingNodeSelector()

    def restart_session(self, *, session_id: str) -> list[str]:
        """Create a replacement planned session for a restartable old session."""
        with self.session_factory() as session:
            old_record = session.get(AccountLiveSessionRecord, session_id)
            if old_record is None:
                return []
            live_task = session.get(LiveTaskRecord, old_record.live_task_id)
            if live_task is None or live_task.status != "running":
                return []
            if self._has_active_session(
                session=session,
                live_task_id=old_record.live_task_id,
                account_id=old_record.account_id,
            ):
                return []
            old_session = self._to_domain(old_record)
            if not old_session.can_auto_restart(max_restarts=self.max_restarts):
                return []
            worker = self._select_restart_worker(
                session=session,
                account_id=old_session.account_id,
                platform=old_session.platform,
            )
            if worker is None:
                return []

            plan = AccountEntryPlan(
                session=AccountLiveSession(
                    id=self.ids.new_id("session"),
                    live_task_id=old_session.live_task_id,
                    platform=old_session.platform,
                    room_url=old_session.room_url,
                    account_id=old_session.account_id,
                    node_id=worker.id,
                    status=AccountLiveSessionStatus.PLANNED,
                    restart_count=old_session.restart_count + 1,
                    cooldown_until=old_session.cooldown_until,
                ),
                queue_name=worker.queue_name,
                delay_seconds=0,
            )

        return self.dispatcher.dispatch([plan])

    def _select_restart_worker(
        self,
        *,
        session: Session,
        account_id: str,
        platform: str,
    ) -> WorkerNode | None:
        active_session_counts = self._load_active_session_counts_by_node(
            session=session
        )
        worker_records = session.scalars(select(WorkerNodeRecord)).all()
        workers = [
            self._to_worker_node(
                record,
                active_session_count=active_session_counts.get(record.id, 0),
            )
            for record in worker_records
        ]
        try:
            return self.selector.select_node(
                account_id=account_id,
                nodes=workers,
                platform=platform,
            )
        except NoAvailableWorkerNode:
            return None

    @staticmethod
    def _load_active_session_counts_by_node(*, session: Session) -> Counter[str]:
        active_statuses = [status.value for status in ACTIVE_SESSION_STATUSES]
        node_ids = session.scalars(
            select(AccountLiveSessionRecord.node_id).where(
                AccountLiveSessionRecord.status.in_(active_statuses)
            )
        ).all()
        return Counter(node_ids)

    @staticmethod
    def _has_active_session(
        *,
        session: Session,
        live_task_id: str,
        account_id: str,
    ) -> bool:
        active_statuses = [status.value for status in ACTIVE_SESSION_STATUSES]
        return (
            session.scalars(
                select(AccountLiveSessionRecord.id).where(
                    AccountLiveSessionRecord.live_task_id == live_task_id,
                    AccountLiveSessionRecord.account_id == account_id,
                    AccountLiveSessionRecord.status.in_(active_statuses),
                )
            ).first()
            is not None
        )

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
            opened_at=record.opened_at,
            last_heartbeat_at=record.last_heartbeat_at,
            last_send_at=record.last_send_at,
            failure_reason=record.failure_reason,
            closed_at=record.closed_at,
            restart_count=record.restart_count,
            cooldown_until=record.cooldown_until,
            send_started_at=record.send_started_at,
        )

    @staticmethod
    def _to_worker_node(
        record: WorkerNodeRecord,
        *,
        active_session_count: int = 0,
    ) -> WorkerNode:
        active_browser_sessions = min(
            record.max_browser_sessions,
            max(record.active_browser_sessions, active_session_count),
        )
        return WorkerNode(
            id=record.id,
            queue_name=record.queue_name,
            supported_platforms=frozenset(record.supported_platforms),
            max_browser_sessions=record.max_browser_sessions,
            active_browser_sessions=active_browser_sessions,
            online=record.online,
        )
