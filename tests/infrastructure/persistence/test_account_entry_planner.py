from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.account_entry_dispatcher import (
    SqlAlchemyAccountEntryDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.account_entry_planner import (
    SqlAlchemyAccountEntryPlanner,
)
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
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
from smhelper.live.application.use_cases.plan_account_entries import (
    PlanAccountEntriesUseCase,
)
from smhelper.workers.domain.rendezvous_hashing import RendezvousHashingNodeSelector


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


def test_account_entry_planner_loads_database_state_and_dispatches_available_accounts() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeEntryTaskPublisher()

    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="running",
                segment_time_seconds=60,
                created_at=now,
            )
        )
        session.add_all(
            [
                PlatformAccountRecord(
                    id="account-1",
                    platform="xhs",
                    display_name="Account 1",
                    enabled=True,
                    daily_send_limit=10,
                    sends_today=0,
                ),
                PlatformAccountRecord(
                    id="account-2",
                    platform="xhs",
                    display_name="Account 2",
                    enabled=True,
                    daily_send_limit=10,
                    sends_today=0,
                ),
                PlatformAccountRecord(
                    id="account-3",
                    platform="xhs",
                    display_name="Account 3",
                    enabled=True,
                    daily_send_limit=10,
                    sends_today=0,
                ),
                PlatformAccountRecord(
                    id="account-4",
                    platform="xhs",
                    display_name="Account 4",
                    enabled=False,
                    daily_send_limit=10,
                    sends_today=0,
                ),
            ]
        )
        session.add_all(
            [
                AccountAuthStateRecord(
                    account_id="account-1",
                    platform="xhs",
                    status="valid",
                    storage_state_path="data/auth/xhs/account-1/storage_state.json",
                ),
                AccountAuthStateRecord(
                    account_id="account-2",
                    platform="xhs",
                    status="valid",
                    storage_state_path="data/auth/xhs/account-2/storage_state.json",
                ),
                AccountAuthStateRecord(
                    account_id="account-3",
                    platform="xhs",
                    status="expired",
                    storage_state_path="data/auth/xhs/account-3/storage_state.json",
                ),
                AccountAuthStateRecord(
                    account_id="account-4",
                    platform="xhs",
                    status="valid",
                    storage_state_path="data/auth/xhs/account-4/storage_state.json",
                ),
            ]
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-existing",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="waiting",
                active_slot_key=AccountLiveSessionRecord.build_active_slot_key(
                    live_task_id="live-1",
                    account_id="account-1",
                    status="waiting",
                ),
            )
        )
        session.add_all(
            [
                WorkerNodeRecord(
                    id="node-a",
                    queue_name="node.node-a.browser",
                    supported_platforms=["xhs"],
                    max_browser_sessions=10,
                    active_browser_sessions=1,
                    online=True,
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
        session.commit()

    dispatched = SqlAlchemyAccountEntryPlanner(
        session_factory=session_factory,
        clock=FixedClock(now),
        planner=PlanAccountEntriesUseCase(
            selector=RendezvousHashingNodeSelector(),
            ids=SequenceIdGenerator(["session-2"]),
            rng=Random(3),
        ),
        dispatcher=SqlAlchemyAccountEntryDispatcher(
            session_factory=session_factory,
            browser_task_publisher=publisher,
        ),
    ).plan_and_dispatch(live_task_id="live-1")

    assert dispatched == ["session-2"]
    assert len(publisher.sent) == 1
    queue_name, payload, countdown_seconds = publisher.sent[0]
    assert queue_name in {"node.node-a.browser", "node.node-b.browser"}
    assert payload == EnterLiveRoomPayload(
        session_id="session-2",
        account_id="account-2",
        live_task_id="live-1",
        room_url="https://example.com/live/1",
        platform="xhs",
    )
    assert countdown_seconds in range(15, 46)

    with Session(engine) as session:
        session_records = session.scalars(
            select(AccountLiveSessionRecord).order_by(AccountLiveSessionRecord.id)
        ).all()
        assert [record.id for record in session_records] == [
            "session-2",
            "session-existing",
        ]
        planned = session.get(AccountLiveSessionRecord, "session-2")
        assert planned is not None
        assert planned.account_id == "account-2"
        assert planned.status == "planned"
        assert planned.active_slot_key == "live-1:account-2"
    engine.dispose()
