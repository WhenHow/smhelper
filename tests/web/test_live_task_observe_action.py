from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ObserveLiveTaskPayload,
)
from smhelper.web.admin import AdminCredentials
from smhelper.web.app import create_app


@dataclass
class FakeCenterTaskPublisher:
    observed: list[tuple[str, ObserveLiveTaskPayload]] = field(default_factory=list)

    def observe_live_task(
        self,
        *,
        queue_name: str,
        payload: ObserveLiveTaskPayload,
    ) -> None:
        self.observed.append((queue_name, payload))


def test_sqladmin_live_task_observe_action_publishes_center_task(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    Base.metadata.create_all(engine)
    publisher = FakeCenterTaskPublisher()
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
        center_task_publisher=publisher,
        center_queue_name="center.custom",
    )
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="pending",
                segment_time_seconds=60,
                created_at=now,
            )
        )
        session.commit()

    with TestClient(app, follow_redirects=False) as client:
        client.post(
            "/admin/login",
            data={"username": "admin", "password": "secret"},
        )
        response = client.get(
            "/admin/live-task-record/action/observe?pks=live-1",
            headers={"Referer": "/admin/live-task-record/list"},
        )

    assert response.status_code == 302
    assert publisher.observed == [
        ("center.custom", ObserveLiveTaskPayload(live_task_id="live-1"))
    ]
    engine.dispose()
