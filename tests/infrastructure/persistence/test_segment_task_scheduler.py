from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    LiveSegmentRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.segment_task_scheduler import (
    SqlAlchemySegmentTaskScheduler,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_session_factory,
)
from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ProcessSegmentPayload,
)


@dataclass
class FakeProcessSegmentPublisher:
    published: list[tuple[str, ProcessSegmentPayload]] = field(default_factory=list)

    def process_segment(
        self,
        *,
        queue_name: str,
        payload: ProcessSegmentPayload,
    ) -> None:
        self.published.append((queue_name, payload))


def test_segment_task_scheduler_persists_and_publishes_completed_segments(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    first = tmp_path / "segment_00000.mp4"
    second = tmp_path / "segment_00001.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    publisher = FakeProcessSegmentPublisher()
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
        session.commit()

    scheduled_ids = SqlAlchemySegmentTaskScheduler(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["segment-1"]),
        clock=FixedClock(now),
        publisher=publisher,
    ).schedule_completed_segments(
        live_task_id="live-1",
        output_dir=tmp_path,
        product_context="Face cream for oily skin.",
        task_context="Ask product-related questions.",
        queue_name="center.live",
    )

    assert scheduled_ids == ["segment-1"]
    assert publisher.published == [
        (
            "center.live",
            ProcessSegmentPayload(
                segment_id="segment-1",
                product_context="Face cream for oily skin.",
                task_context="Ask product-related questions.",
            ),
        )
    ]
    with Session(engine) as session:
        segment = session.get(LiveSegmentRecord, "segment-1")
        assert segment is not None
        assert segment.live_task_id == "live-1"
        assert segment.sequence == 0
        assert segment.video_path == str(first)
        assert segment.completed is False
        assert segment.created_at == now.replace(tzinfo=None)
    engine.dispose()


def test_segment_task_scheduler_does_not_publish_existing_segment_twice(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    first = tmp_path / "segment_00000.mp4"
    second = tmp_path / "segment_00001.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    publisher = FakeProcessSegmentPublisher()
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
        session.add(
            LiveSegmentRecord(
                id="segment-existing",
                live_task_id="live-1",
                sequence=0,
                video_path=str(first),
                completed=False,
                created_at=now,
            )
        )
        session.commit()

    scheduled_ids = SqlAlchemySegmentTaskScheduler(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["segment-new"]),
        clock=FixedClock(now),
        publisher=publisher,
    ).schedule_completed_segments(
        live_task_id="live-1",
        output_dir=tmp_path,
        product_context="Face cream for oily skin.",
        task_context="Ask product-related questions.",
        queue_name="center.live",
    )

    assert scheduled_ids == []
    assert publisher.published == []
    with Session(engine) as session:
        assert session.query(LiveSegmentRecord).count() == 1
    engine.dispose()
