"""SQLAlchemy-backed live-task termination orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.clock import Clock
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord


class LiveTaskShutdownCoordinator(Protocol):
    """Coordinates account session shutdown after a live task ends."""

    def close_active_sessions(self, *, live_task_id: str) -> list[str]:
        """Close or mark active account sessions for the live task."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyLiveTaskTerminator:
    """Mark a live task as ended and trigger account-session shutdown."""

    session_factory: sessionmaker[Session]
    clock: Clock
    shutdown_coordinator: LiveTaskShutdownCoordinator

    def end_live_task(
        self,
        *,
        live_task_id: str,
        failure_reason: str | None = None,
    ) -> list[str]:
        """Persist terminal live-task state and close active account sessions."""
        now = self.clock.now()

        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if live_task is None:
                return []
            live_task.status = "ended"
            live_task.ended_at = now
            live_task.failure_reason = failure_reason
            session.commit()

        return self.shutdown_coordinator.close_active_sessions(
            live_task_id=live_task_id,
        )
