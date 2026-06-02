from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from smhelper.infrastructure.persistence.sqlalchemy.account_entry_dispatcher import (
    SqlAlchemyAccountEntryDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import AccountLiveSessionRecord
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.task_queue.celery.publisher import EnterLiveRoomPayload
from smhelper.live.application.use_cases.plan_account_entries import AccountEntryPlan
from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)


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


def test_account_entry_dispatcher_persists_sessions_and_publishes_delayed_tasks() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    publisher = FakeEntryTaskPublisher()

    dispatched = SqlAlchemyAccountEntryDispatcher(
        session_factory=session_factory,
        browser_task_publisher=publisher,
    ).dispatch(
        plans=[
            AccountEntryPlan(
                session=AccountLiveSession(
                    id="session-1",
                    live_task_id="live-1",
                    platform="xhs",
                    room_url="https://example.com/live/1",
                    account_id="account-1",
                    node_id="node-a",
                    status=AccountLiveSessionStatus.PLANNED,
                ),
                queue_name="node.node-a.browser",
                delay_seconds=17,
            )
        ]
    )

    assert dispatched == ["session-1"]
    assert publisher.sent == [
        (
            "node.node-a.browser",
            EnterLiveRoomPayload(
                session_id="session-1",
                account_id="account-1",
                live_task_id="live-1",
                room_url="https://example.com/live/1",
                platform="xhs",
            ),
            17,
        )
    ]
    with Session(engine) as session:
        record = session.get(AccountLiveSessionRecord, "session-1")
        assert record is not None
        assert record.status == "planned"
        assert record.active_slot_key == "live-1:account-1"
        assert record.account_id == "account-1"
        assert record.node_id == "node-a"
    engine.dispose()


def test_account_entry_dispatcher_skips_existing_active_account_session() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    publisher = FakeEntryTaskPublisher()
    with Session(engine) as session:
        session.add(
            AccountLiveSessionRecord(
                id="session-existing",
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

    dispatched = SqlAlchemyAccountEntryDispatcher(
        session_factory=session_factory,
        browser_task_publisher=publisher,
    ).dispatch(
        plans=[
            AccountEntryPlan(
                session=AccountLiveSession(
                    id="session-new",
                    live_task_id="live-1",
                    platform="xhs",
                    room_url="https://example.com/live/1",
                    account_id="account-1",
                    node_id="node-b",
                    status=AccountLiveSessionStatus.PLANNED,
                ),
                queue_name="node.node-b.browser",
                delay_seconds=17,
            )
        ]
    )

    assert dispatched == []
    assert publisher.sent == []
    with Session(engine) as session:
        existing = session.get(AccountLiveSessionRecord, "session-existing")
        duplicate = session.get(AccountLiveSessionRecord, "session-new")
        assert existing is not None
        assert existing.status == "waiting"
        assert duplicate is None
    engine.dispose()
