from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from smhelper.infrastructure.persistence.sqlalchemy.account_session_health_checker import (
    SqlAlchemyAccountSessionHealthChecker,
)
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import CheckSessionPayload


@dataclass
class FakeBrowserTaskPublisher:
    checks: list[tuple[str, CheckSessionPayload]] = field(default_factory=list)

    def check_session(
        self,
        *,
        queue_name: str,
        payload: CheckSessionPayload,
    ) -> None:
        self.checks.append((queue_name, payload))


def test_account_session_health_checker_publishes_checks_for_open_sessions() -> None:
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    publisher = FakeBrowserTaskPublisher()
    with Session(engine) as session:
        session.add_all(
            [
                WorkerNodeRecord(
                    id="node-a",
                    queue_name="node.node-a.browser",
                    supported_platforms=["xhs"],
                    max_browser_sessions=10,
                    active_browser_sessions=2,
                    online=True,
                ),
                WorkerNodeRecord(
                    id="node-b",
                    queue_name="node.node-b.browser",
                    supported_platforms=["xhs"],
                    max_browser_sessions=10,
                    active_browser_sessions=1,
                    online=True,
                ),
                WorkerNodeRecord(
                    id="node-offline",
                    queue_name="node.offline.browser",
                    supported_platforms=["xhs"],
                    max_browser_sessions=10,
                    active_browser_sessions=1,
                    online=False,
                ),
            ]
        )
        session.add_all(
            [
                _session_record("session-waiting", "live-1", "node-a", "waiting", now),
                _session_record("session-sending", "live-1", "node-b", "sending", now),
                _session_record("session-planned", "live-1", "node-a", "planned", now),
                _session_record("session-closed", "live-1", "node-a", "closed", now),
                _session_record(
                    "session-offline",
                    "live-1",
                    "node-offline",
                    "waiting",
                    now,
                ),
                _session_record(
                    "session-other-live", "live-2", "node-a", "waiting", now
                ),
            ]
        )
        session.commit()

    checked_session_ids = SqlAlchemyAccountSessionHealthChecker(
        session_factory=session_factory,
        browser_task_publisher=publisher,
    ).check_live_task_sessions(live_task_id="live-1")

    assert checked_session_ids == ["session-sending", "session-waiting"]
    assert publisher.checks == [
        ("node.node-b.browser", CheckSessionPayload(session_id="session-sending")),
        ("node.node-a.browser", CheckSessionPayload(session_id="session-waiting")),
    ]
    engine.dispose()


def _session_record(
    session_id: str,
    live_task_id: str,
    node_id: str,
    status: str,
    now: datetime,
) -> AccountLiveSessionRecord:
    active_slot_key = (
        f"{live_task_id}:account-{session_id}"
        if status in {"waiting", "sending"}
        else None
    )
    return AccountLiveSessionRecord(
        id=session_id,
        live_task_id=live_task_id,
        platform="xhs",
        room_url=f"https://example.com/{live_task_id}",
        account_id=f"account-{session_id}",
        node_id=node_id,
        status=status,
        active_slot_key=active_slot_key,
        opened_at=now,
    )
