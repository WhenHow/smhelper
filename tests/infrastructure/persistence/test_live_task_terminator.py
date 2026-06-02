from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.live_task_terminator import (
    SqlAlchemyLiveTaskTerminator,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)


@dataclass
class FakeShutdownCoordinator:
    closed_live_task_ids: list[str] = field(default_factory=list)
    closed_session_ids: list[str] = field(default_factory=lambda: ["session-1"])

    def close_active_sessions(self, *, live_task_id: str) -> list[str]:
        self.closed_live_task_ids.append(live_task_id)
        return self.closed_session_ids


def test_live_task_terminator_marks_task_ended_and_closes_sessions() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 13, 0, tzinfo=UTC)
    shutdown_coordinator = FakeShutdownCoordinator()
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="running",
                created_at=now,
                started_at=now,
            )
        )
        session.commit()

    closed_session_ids = SqlAlchemyLiveTaskTerminator(
        session_factory=session_factory,
        clock=FixedClock(now),
        shutdown_coordinator=shutdown_coordinator,
    ).end_live_task(live_task_id="live-1", failure_reason=None)

    assert closed_session_ids == ["session-1"]
    assert shutdown_coordinator.closed_live_task_ids == ["live-1"]
    with Session(engine) as session:
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.status == "ended"
        assert live_task.ended_at == now.replace(tzinfo=None)
        assert live_task.failure_reason is None
    engine.dispose()


def test_live_task_terminator_returns_empty_without_closing_missing_task() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 13, 0, tzinfo=UTC)
    shutdown_coordinator = FakeShutdownCoordinator()

    closed_session_ids = SqlAlchemyLiveTaskTerminator(
        session_factory=session_factory,
        clock=FixedClock(now),
        shutdown_coordinator=shutdown_coordinator,
    ).end_live_task(live_task_id="missing-live", failure_reason="not_found")

    assert closed_session_ids == []
    assert shutdown_coordinator.closed_live_task_ids == []
    engine.dispose()
