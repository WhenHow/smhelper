from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    DispatchJobRecord,
    SendAttemptRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_shutdown_coordinator import (
    SqlAlchemyLiveTaskShutdownCoordinator,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import CloseSessionPayload
from smhelper.live.domain.policies.shutdown_policy import LiveTaskShutdownPolicy


@dataclass
class FakeCloseTaskPublisher:
    sent: list[tuple[str, CloseSessionPayload]] = field(default_factory=list)

    def close_session(
        self,
        *,
        queue_name: str,
        payload: CloseSessionPayload,
    ) -> None:
        self.sent.append((queue_name, payload))


def test_shutdown_coordinator_marks_waiting_session_closing_and_publishes_close() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
    publisher = FakeCloseTaskPublisher()
    with Session(engine) as session:
        session.add(
            WorkerNodeRecord(
                id="node-a",
                queue_name="node.node-a.browser",
                supported_platforms=["xhs"],
                max_browser_sessions=10,
                active_browser_sessions=1,
                online=True,
            )
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-1",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="waiting",
                active_slot_key="live-1:account-1",
            )
        )
        session.commit()

    closed = SqlAlchemyLiveTaskShutdownCoordinator(
        session_factory=session_factory,
        clock=FixedClock(now),
        shutdown_policy=LiveTaskShutdownPolicy(),
        browser_task_publisher=publisher,
    ).close_active_sessions(live_task_id="live-1")

    assert closed == ["session-1"]
    assert publisher.sent == [
        (
            "node.node-a.browser",
            CloseSessionPayload(session_id="session-1", reason="live_ended"),
        )
    ]
    with Session(engine) as session:
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        assert live_session is not None
        assert live_session.status == "closing"
        assert live_session.active_slot_key == "live-1:account-1"
        assert live_session.failure_reason == "live_ended"
    engine.dispose()


def test_shutdown_coordinator_marks_timed_out_sending_session_lost() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
    publisher = FakeCloseTaskPublisher()
    with Session(engine) as session:
        session.add(
            WorkerNodeRecord(
                id="node-a",
                queue_name="node.node-a.browser",
                supported_platforms=["xhs"],
                max_browser_sessions=10,
                active_browser_sessions=1,
                online=True,
            )
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-1",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="sending",
                active_slot_key="live-1:account-1",
                send_started_at=now - timedelta(seconds=31),
            )
        )
        session.commit()

    closed = SqlAlchemyLiveTaskShutdownCoordinator(
        session_factory=session_factory,
        clock=FixedClock(now),
        shutdown_policy=LiveTaskShutdownPolicy(grace_period_seconds=30),
        browser_task_publisher=publisher,
    ).close_active_sessions(live_task_id="live-1")

    assert closed == ["session-1"]
    assert publisher.sent == []
    with Session(engine) as session:
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        assert live_session is not None
        assert live_session.status == "lost"
        assert live_session.active_slot_key is None
        assert live_session.failure_reason == "shutdown_timeout"
        assert live_session.closed_at == now.replace(tzinfo=None)
        assert live_session.send_started_at is None
    engine.dispose()


def test_shutdown_coordinator_fails_running_dispatch_job_for_timed_out_sending_session() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
    publisher = FakeCloseTaskPublisher()
    with Session(engine) as session:
        session.add(
            AccountLiveSessionRecord(
                id="session-1",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="sending",
                active_slot_key="live-1:account-1",
                send_started_at=now - timedelta(seconds=31),
            )
        )
        session.add(
            DispatchJobRecord(
                id="job-1",
                candidate_question_id="candidate-1",
                live_task_id="live-1",
                account_live_session_id="session-1",
                account_id="account-1",
                final_text="Is this suitable for oily skin?",
                status="running",
                created_at=now - timedelta(minutes=1),
                started_at=now - timedelta(seconds=31),
            )
        )
        session.commit()

    closed = SqlAlchemyLiveTaskShutdownCoordinator(
        session_factory=session_factory,
        clock=FixedClock(now),
        shutdown_policy=LiveTaskShutdownPolicy(grace_period_seconds=30),
        browser_task_publisher=publisher,
    ).close_active_sessions(live_task_id="live-1")

    assert closed == ["session-1"]
    assert publisher.sent == []
    with Session(engine) as session:
        job = session.get(DispatchJobRecord, "job-1")
        attempts = session.query(SendAttemptRecord).all()
        assert job is not None
        assert job.status == "failed"
        assert job.finished_at == now.replace(tzinfo=None)
        assert job.failure_reason == "shutdown_timeout"
        assert len(attempts) == 1
        assert attempts[0].dispatch_job_id == "job-1"
        assert attempts[0].account_live_session_id == "session-1"
        assert attempts[0].account_id == "account-1"
        assert attempts[0].status == "failed"
        assert attempts[0].success_detection == "operation_completed"
        assert attempts[0].attempted_at == now.replace(tzinfo=None)
        assert attempts[0].failure_reason == "shutdown_timeout"
    engine.dispose()
