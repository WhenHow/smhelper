"""SQLAlchemy-backed center orchestration for account live-room entry."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.accounts.domain.account_auth_state import (
    AccountAuthState,
    AccountAuthStatus,
)
from smhelper.accounts.domain.account_node_binding import AccountNodeBinding
from smhelper.accounts.domain.platform_account import PlatformAccount
from smhelper.core.clock import Clock
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.live.application.use_cases.plan_account_entries import (
    AccountEntryCandidate,
    AccountEntryPlan,
    PlanAccountEntriesUseCase,
)
from smhelper.live.domain.account_live_session import (
    ACTIVE_SESSION_STATUSES,
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.workers.domain.worker_node import WorkerNode


class AccountEntryDispatcher(Protocol):
    """Persists planned account sessions and publishes node tasks."""

    def dispatch(self, plans: list[AccountEntryPlan]) -> list[str]:
        """Dispatch already planned account-entry tasks."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyAccountEntryPlanner:
    """Load center state, plan account entry, then dispatch the plans."""

    session_factory: sessionmaker[Session]
    clock: Clock
    planner: PlanAccountEntriesUseCase
    dispatcher: AccountEntryDispatcher

    def plan_and_dispatch(self, *, live_task_id: str) -> list[str]:
        """Plan and dispatch account entry tasks for one live task."""
        now = self.clock.now()
        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if live_task is None:
                return []
            if live_task.status != "running":
                return []
            candidates = self._load_candidates(
                session=session,
                platform=live_task.platform,
            )
            nodes = self._load_nodes(session=session)
            existing_sessions = self._load_existing_sessions(
                session=session,
                live_task_id=live_task_id,
            )

        plans = self.planner.plan(
            live_task_id=live_task.id,
            platform=live_task.platform,
            room_url=live_task.room_url,
            candidates=candidates,
            nodes=nodes,
            existing_sessions=existing_sessions,
            now=now,
        )
        return self.dispatcher.dispatch(plans)

    @staticmethod
    def _load_candidates(
        *,
        session: Session,
        platform: str,
    ) -> list[AccountEntryCandidate]:
        accounts = session.scalars(
            select(PlatformAccountRecord).where(
                PlatformAccountRecord.platform == platform
            )
        ).all()
        auth_states = {
            record.account_id: record
            for record in session.scalars(
                select(AccountAuthStateRecord).where(
                    AccountAuthStateRecord.platform == platform
                )
            ).all()
        }
        candidates: list[AccountEntryCandidate] = []
        for account in accounts:
            auth_state = auth_states.get(account.id)
            if auth_state is None:
                continue
            candidates.append(
                AccountEntryCandidate(
                    account=SqlAlchemyAccountEntryPlanner._to_account(account),
                    auth_state=SqlAlchemyAccountEntryPlanner._to_auth_state(auth_state),
                    # Binding persistence is not present yet; the domain's empty
                    # binding means the account may use any eligible node.
                    node_binding=AccountNodeBinding(
                        account_id=account.id,
                        allowed_node_ids=frozenset(),
                    ),
                )
            )
        return candidates

    @staticmethod
    def _load_nodes(*, session: Session) -> list[WorkerNode]:
        active_session_counts = (
            SqlAlchemyAccountEntryPlanner._load_active_session_counts_by_node(
                session=session
            )
        )
        records = session.scalars(select(WorkerNodeRecord)).all()
        return [
            SqlAlchemyAccountEntryPlanner._to_node(
                record,
                active_session_count=active_session_counts.get(record.id, 0),
            )
            for record in records
        ]

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
    def _load_existing_sessions(
        *,
        session: Session,
        live_task_id: str,
    ) -> list[AccountLiveSession]:
        records = session.scalars(
            select(AccountLiveSessionRecord).where(
                AccountLiveSessionRecord.live_task_id == live_task_id
            )
        ).all()
        return [
            SqlAlchemyAccountEntryPlanner._to_live_session(record) for record in records
        ]

    @staticmethod
    def _to_account(record: PlatformAccountRecord) -> PlatformAccount:
        return PlatformAccount(
            id=record.id,
            platform=record.platform,
            display_name=record.display_name,
            enabled=record.enabled,
            daily_send_limit=record.daily_send_limit,
            sends_today=record.sends_today,
            cooldown_until=_as_aware_utc(record.cooldown_until),
        )

    @staticmethod
    def _to_auth_state(record: AccountAuthStateRecord) -> AccountAuthState:
        return AccountAuthState(
            account_id=record.account_id,
            platform=record.platform,
            status=AccountAuthStatus(record.status),
            storage_state_path=record.storage_state_path,
            failure_reason=record.failure_reason,
        )

    @staticmethod
    def _to_node(
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

    @staticmethod
    def _to_live_session(record: AccountLiveSessionRecord) -> AccountLiveSession:
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
