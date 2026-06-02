from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.live_task_observer import (
    SqlAlchemyLiveTaskObserverRunner,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_starter import (
    SqlAlchemyLiveTaskStarter,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_terminator import (
    SqlAlchemyLiveTaskTerminator,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.live.application.ports.live_stream_observer import (
    LiveStreamObservation,
    LiveStreamObservationStatus,
)


@dataclass
class FakeLiveStreamObserver:
    observation: LiveStreamObservation
    observed_urls: list[str] = field(default_factory=list)

    def observe(self, *, room_url: str) -> LiveStreamObservation:
        self.observed_urls.append(room_url)
        return self.observation


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
        return ["session-1"]


@dataclass
class FakeShutdownCoordinator:
    closed_live_task_ids: list[str] = field(default_factory=list)

    def close_active_sessions(self, *, live_task_id: str) -> list[str]:
        self.closed_live_task_ids.append(live_task_id)
        return []


def test_live_task_observer_runner_starts_live_task_when_stream_is_discovered(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    process_starter = FakeProcessStarter()
    entry_planner = FakeAccountEntryPlanner()
    shutdown_coordinator = FakeShutdownCoordinator()
    observer = FakeLiveStreamObserver(
        LiveStreamObservation(
            status=LiveStreamObservationStatus.LIVE,
            stream_url="https://stream.example/live.flv",
        )
    )
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/livestream/1",
                status="pending",
                segment_time_seconds=60,
                created_at=now,
            )
        )
        session.commit()

    result = SqlAlchemyLiveTaskObserverRunner(
        session_factory=session_factory,
        observer=observer,
        starter=SqlAlchemyLiveTaskStarter(
            session_factory=session_factory,
            clock=FixedClock(now),
            process_starter=process_starter,
            account_entry_planner=entry_planner,
            media_root=tmp_path,
            ffmpeg_path="ffmpeg-custom",
        ),
        terminator=SqlAlchemyLiveTaskTerminator(
            session_factory=session_factory,
            clock=FixedClock(now),
            shutdown_coordinator=shutdown_coordinator,
        ),
    ).run_once(live_task_id="live-1")

    assert result is not None
    assert result.status is LiveStreamObservationStatus.LIVE
    assert result.stream_url == "https://stream.example/live.flv"
    assert result.start_result is not None
    assert result.start_result.entry_session_ids == ["session-1"]
    assert observer.observed_urls == ["https://example.com/livestream/1"]
    assert process_starter.commands[0][0:4] == [
        "ffmpeg-custom",
        "-y",
        "-i",
        "https://stream.example/live.flv",
    ]
    assert entry_planner.dispatched_live_task_ids == ["live-1"]
    assert shutdown_coordinator.closed_live_task_ids == []
    with Session(engine) as session:
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.status == "running"
        assert live_task.stream_url == "https://stream.example/live.flv"
    engine.dispose()


def test_live_task_observer_runner_ends_task_when_room_is_not_live(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    observer = FakeLiveStreamObserver(
        LiveStreamObservation(status=LiveStreamObservationStatus.NOT_LIVE)
    )
    process_starter = FakeProcessStarter()
    entry_planner = FakeAccountEntryPlanner()
    shutdown_coordinator = FakeShutdownCoordinator()
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/livestream/1",
                status="pending",
                segment_time_seconds=60,
                created_at=now,
            )
        )
        session.commit()

    result = SqlAlchemyLiveTaskObserverRunner(
        session_factory=session_factory,
        observer=observer,
        starter=SqlAlchemyLiveTaskStarter(
            session_factory=session_factory,
            clock=FixedClock(now),
            process_starter=process_starter,
            account_entry_planner=entry_planner,
            media_root=tmp_path,
            ffmpeg_path="ffmpeg-custom",
        ),
        terminator=SqlAlchemyLiveTaskTerminator(
            session_factory=session_factory,
            clock=FixedClock(now),
            shutdown_coordinator=shutdown_coordinator,
        ),
    ).run_once(live_task_id="live-1")

    assert result is not None
    assert result.status is LiveStreamObservationStatus.NOT_LIVE
    assert result.start_result is None
    assert process_starter.commands == []
    assert entry_planner.dispatched_live_task_ids == []
    assert shutdown_coordinator.closed_live_task_ids == ["live-1"]
    with Session(engine) as session:
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.status == "ended"
        assert live_task.ended_at == now.replace(tzinfo=None)
        assert live_task.failure_reason == "live_not_active"
    engine.dispose()


def test_live_task_observer_runner_records_unknown_status_without_starting(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    observer = FakeLiveStreamObserver(
        LiveStreamObservation(status=LiveStreamObservationStatus.UNKNOWN)
    )
    process_starter = FakeProcessStarter()
    entry_planner = FakeAccountEntryPlanner()
    shutdown_coordinator = FakeShutdownCoordinator()
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/livestream/1",
                status="pending",
                segment_time_seconds=60,
                created_at=now,
            )
        )
        session.commit()

    result = SqlAlchemyLiveTaskObserverRunner(
        session_factory=session_factory,
        observer=observer,
        starter=SqlAlchemyLiveTaskStarter(
            session_factory=session_factory,
            clock=FixedClock(now),
            process_starter=process_starter,
            account_entry_planner=entry_planner,
            media_root=tmp_path,
            ffmpeg_path="ffmpeg-custom",
        ),
        terminator=SqlAlchemyLiveTaskTerminator(
            session_factory=session_factory,
            clock=FixedClock(now),
            shutdown_coordinator=shutdown_coordinator,
        ),
    ).run_once(live_task_id="live-1")

    assert result is not None
    assert result.status is LiveStreamObservationStatus.UNKNOWN
    assert result.start_result is None
    assert process_starter.commands == []
    assert shutdown_coordinator.closed_live_task_ids == []
    with Session(engine) as session:
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.status == "pending"
        assert live_task.failure_reason == "live_status_unknown"
    engine.dispose()


def test_live_task_observer_runner_requires_stream_url_for_live_room(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    observer = FakeLiveStreamObserver(
        LiveStreamObservation(status=LiveStreamObservationStatus.LIVE)
    )
    process_starter = FakeProcessStarter()
    entry_planner = FakeAccountEntryPlanner()
    shutdown_coordinator = FakeShutdownCoordinator()
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/livestream/1",
                status="pending",
                segment_time_seconds=60,
                created_at=now,
            )
        )
        session.commit()

    result = SqlAlchemyLiveTaskObserverRunner(
        session_factory=session_factory,
        observer=observer,
        starter=SqlAlchemyLiveTaskStarter(
            session_factory=session_factory,
            clock=FixedClock(now),
            process_starter=process_starter,
            account_entry_planner=entry_planner,
            media_root=tmp_path,
            ffmpeg_path="ffmpeg-custom",
        ),
        terminator=SqlAlchemyLiveTaskTerminator(
            session_factory=session_factory,
            clock=FixedClock(now),
            shutdown_coordinator=shutdown_coordinator,
        ),
    ).run_once(live_task_id="live-1")

    assert result is not None
    assert result.status is LiveStreamObservationStatus.LIVE
    assert result.start_result is None
    assert process_starter.commands == []
    assert shutdown_coordinator.closed_live_task_ids == []
    with Session(engine) as session:
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.status == "pending"
        assert live_task.failure_reason == "stream_url_not_found"
    engine.dispose()
