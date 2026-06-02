from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.live_task_starter import (
    LiveTaskStartResult,
    SqlAlchemyLiveTaskStarter,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)


@dataclass
class FakeProcessStarter:
    commands: list[list[str]] = field(default_factory=list)

    def start(self, command: list[str]) -> None:
        self.commands.append(command)


@dataclass
class FakeAccountEntryPlanner:
    dispatched_live_task_ids: list[str] = field(default_factory=list)

    def plan_and_dispatch(self, *, live_task_id: str) -> list[str]:
        self.dispatched_live_task_ids.append(live_task_id)
        return ["session-1", "session-2"]


def test_live_task_starter_marks_task_running_starts_recorder_and_plans_entries(
    tmp_path: Path,
) -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    process_starter = FakeProcessStarter()
    entry_planner = FakeAccountEntryPlanner()

    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/livestream/1",
                status="pending",
                segment_time_seconds=30,
                created_at=now,
            )
        )
        session.commit()

    result = SqlAlchemyLiveTaskStarter(
        session_factory=session_factory,
        clock=FixedClock(now),
        process_starter=process_starter,
        account_entry_planner=entry_planner,
        media_root=tmp_path,
        ffmpeg_path="ffmpeg-custom",
    ).start_live_task(
        live_task_id="live-1",
        stream_url="https://stream.example/live.flv",
    )

    assert result == LiveTaskStartResult(
        live_task_id="live-1",
        output_dir=tmp_path / "live-1",
        entry_session_ids=["session-1", "session-2"],
    )
    assert (tmp_path / "live-1").is_dir()
    assert process_starter.commands == [
        [
            "ffmpeg-custom",
            "-y",
            "-i",
            "https://stream.example/live.flv",
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            "30",
            "-reset_timestamps",
            "1",
            str(tmp_path / "live-1" / "segment_%05d.mp4"),
        ]
    ]
    assert entry_planner.dispatched_live_task_ids == ["live-1"]
    with Session(engine) as session:
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.status == "running"
        assert live_task.stream_url == "https://stream.example/live.flv"
        assert live_task.started_at == now.replace(tzinfo=None)
    engine.dispose()


def test_live_task_starter_does_not_restart_running_task(tmp_path: Path) -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    process_starter = FakeProcessStarter()
    entry_planner = FakeAccountEntryPlanner()

    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/livestream/1",
                status="running",
                stream_url="https://stream.example/existing.flv",
                segment_time_seconds=60,
                created_at=now,
                started_at=now,
            )
        )
        session.commit()

    result = SqlAlchemyLiveTaskStarter(
        session_factory=session_factory,
        clock=FixedClock(now),
        process_starter=process_starter,
        account_entry_planner=entry_planner,
        media_root=tmp_path,
        ffmpeg_path="ffmpeg-custom",
    ).start_live_task(
        live_task_id="live-1",
        stream_url="https://stream.example/new.flv",
    )

    assert result is None
    assert process_starter.commands == []
    assert entry_planner.dispatched_live_task_ids == []
    with Session(engine) as session:
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.status == "running"
        assert live_task.stream_url == "https://stream.example/existing.flv"
    engine.dispose()
