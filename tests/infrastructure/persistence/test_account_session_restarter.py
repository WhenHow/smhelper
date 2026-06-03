from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.account_entry_dispatcher import (
    SqlAlchemyAccountEntryDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.account_session_restarter import (
    SqlAlchemyAccountSessionRestarter,
)
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import EnterLiveRoomPayload


@dataclass
class FakeEntryTaskPublisher:
    sent: list[tuple[str, EnterLiveRoomPayload, int]] = field(default_factory=list)

    def enter_live_room(
        self,
        *,
        queue_name: str,
        payload: EnterLiveRoomPayload,
        countdown_seconds: int,
    ) -> None:
        self.sent.append((queue_name, payload, countdown_seconds))


def test_account_session_restarter_rebuilds_failed_session_once() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    publisher = FakeEntryTaskPublisher()
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="running",
                segment_time_seconds=60,
                created_at=now,
                started_at=now,
            )
        )
        session.add(
            WorkerNodeRecord(
                id="node-a",
                queue_name="node.node-a.browser",
                supported_platforms=["xhs"],
                max_browser_sessions=10,
                active_browser_sessions=0,
                online=True,
            )
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-old",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="failed",
                active_slot_key=None,
                closed_at=now,
                restart_count=1,
                failure_reason="browser_crashed",
            )
        )
        session.commit()

    rebuilt = SqlAlchemyAccountSessionRestarter(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["session-new"]),
        dispatcher=SqlAlchemyAccountEntryDispatcher(
            session_factory=session_factory,
            browser_task_publisher=publisher,
        ),
        max_restarts=2,
    ).restart_session(session_id="session-old")

    assert rebuilt == ["session-new"]
    assert publisher.sent == [
        (
            "node.node-a.browser",
            EnterLiveRoomPayload(
                session_id="session-new",
                account_id="account-1",
                live_task_id="live-1",
                room_url="https://example.com/live/1",
                platform="xhs",
            ),
            0,
        )
    ]
    with Session(engine) as session:
        old_record = session.get(AccountLiveSessionRecord, "session-old")
        new_record = session.get(AccountLiveSessionRecord, "session-new")
        assert old_record is not None
        assert old_record.status == "failed"
        assert old_record.active_slot_key is None
        assert new_record is not None
        assert new_record.status == "planned"
        assert new_record.restart_count == 2
        assert new_record.active_slot_key == "live-1:account-1"
    engine.dispose()


def test_account_session_restarter_skips_when_restart_limit_is_reached() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    publisher = FakeEntryTaskPublisher()
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="running",
                segment_time_seconds=60,
                created_at=now,
                started_at=now,
            )
        )
        session.add(
            WorkerNodeRecord(
                id="node-a",
                queue_name="node.node-a.browser",
                supported_platforms=["xhs"],
                max_browser_sessions=10,
                active_browser_sessions=0,
                online=True,
            )
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-old",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="lost",
                active_slot_key=None,
                closed_at=now,
                restart_count=2,
                failure_reason="worker_timeout",
            )
        )
        session.commit()

    rebuilt = SqlAlchemyAccountSessionRestarter(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["session-new"]),
        dispatcher=SqlAlchemyAccountEntryDispatcher(
            session_factory=session_factory,
            browser_task_publisher=publisher,
        ),
        max_restarts=2,
    ).restart_session(session_id="session-old")

    assert rebuilt == []
    assert publisher.sent == []
    with Session(engine) as session:
        assert session.get(AccountLiveSessionRecord, "session-new") is None
    engine.dispose()


def test_account_session_restarter_uses_available_hrw_node_when_old_node_is_offline() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    publisher = FakeEntryTaskPublisher()
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="running",
                segment_time_seconds=60,
                created_at=now,
                started_at=now,
            )
        )
        session.add_all(
            [
                WorkerNodeRecord(
                    id="node-a",
                    queue_name="node.node-a.browser",
                    supported_platforms=["xhs"],
                    max_browser_sessions=10,
                    active_browser_sessions=0,
                    online=False,
                ),
                WorkerNodeRecord(
                    id="node-b",
                    queue_name="node.node-b.browser",
                    supported_platforms=["xhs"],
                    max_browser_sessions=10,
                    active_browser_sessions=0,
                    online=True,
                ),
            ]
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-old",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="failed",
                active_slot_key=None,
                closed_at=now,
                restart_count=0,
                failure_reason="browser_crashed",
            )
        )
        session.commit()

    rebuilt = SqlAlchemyAccountSessionRestarter(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["session-new"]),
        dispatcher=SqlAlchemyAccountEntryDispatcher(
            session_factory=session_factory,
            browser_task_publisher=publisher,
        ),
        max_restarts=2,
    ).restart_session(session_id="session-old")

    assert rebuilt == ["session-new"]
    assert publisher.sent == [
        (
            "node.node-b.browser",
            EnterLiveRoomPayload(
                session_id="session-new",
                account_id="account-1",
                live_task_id="live-1",
                room_url="https://example.com/live/1",
                platform="xhs",
            ),
            0,
        )
    ]
    with Session(engine) as session:
        new_record = session.get(AccountLiveSessionRecord, "session-new")
        assert new_record is not None
        assert new_record.node_id == "node-b"
        assert new_record.active_slot_key == "live-1:account-1"
    engine.dispose()
