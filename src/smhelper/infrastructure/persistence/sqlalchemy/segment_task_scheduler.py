"""SQLAlchemy-backed scheduler for completed segment processing tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.clock import Clock
from smhelper.core.ids import IdGenerator
from smhelper.infrastructure.media.ffmpeg.segment_scanner import SegmentScanner
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    LiveSegmentRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ProcessSegmentPayload,
)


class ProcessSegmentTaskPublisher(Protocol):
    """Publisher capable of scheduling center-side segment processing."""

    def process_segment(
        self,
        *,
        queue_name: str,
        payload: ProcessSegmentPayload,
    ) -> None:
        """Publish one completed-segment processing task."""


@dataclass(frozen=True, slots=True)
class SqlAlchemySegmentTaskScheduler:
    """Persist newly completed segment files and publish processing tasks."""

    session_factory: sessionmaker[Session]
    ids: IdGenerator
    clock: Clock
    publisher: ProcessSegmentTaskPublisher
    media_root: Path | None = None
    queue_name: str | None = None

    def schedule_live_task_segments(
        self,
        *,
        live_task_id: str,
        include_last: bool = False,
        media_root: Path | None = None,
        queue_name: str | None = None,
    ) -> list[str]:
        """Schedule completed segments using context stored on the LiveTask."""
        resolved_media_root = media_root or self.media_root
        resolved_queue_name = queue_name or self.queue_name
        if resolved_media_root is None:
            raise ValueError("media_root must be configured")
        if resolved_queue_name is None:
            raise ValueError("queue_name must be configured")

        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if live_task is None:
                return []
            product_context = live_task.product_context or ""
            task_context = live_task.task_context or ""

        return self.schedule_completed_segments(
            live_task_id=live_task_id,
            output_dir=resolved_media_root / live_task_id,
            product_context=product_context,
            task_context=task_context,
            queue_name=resolved_queue_name,
            include_last=include_last,
        )

    def schedule_completed_segments(
        self,
        *,
        live_task_id: str,
        output_dir: Path,
        product_context: str,
        task_context: str,
        queue_name: str,
        include_last: bool = False,
    ) -> list[str]:
        """Create records for newly completed segment files and publish tasks."""
        paths = SegmentScanner(output_dir=output_dir).completed_segments(
            include_last=include_last
        )
        scheduled_payloads = self._persist_new_segments(
            live_task_id=live_task_id,
            paths=paths,
            product_context=product_context,
            task_context=task_context,
        )
        for payload in scheduled_payloads:
            self.publisher.process_segment(queue_name=queue_name, payload=payload)
        return [payload.segment_id for payload in scheduled_payloads]

    def _persist_new_segments(
        self,
        *,
        live_task_id: str,
        paths: list[Path],
        product_context: str,
        task_context: str,
    ) -> list[ProcessSegmentPayload]:
        now = self.clock.now()
        payloads: list[ProcessSegmentPayload] = []
        with self.session_factory() as session:
            if session.get(LiveTaskRecord, live_task_id) is None:
                return []
            existing_paths = self._load_existing_paths(
                session=session,
                live_task_id=live_task_id,
                paths=paths,
            )
            for path in paths:
                if str(path) in existing_paths:
                    continue
                segment_id = self.ids.new_id("segment")
                session.add(
                    LiveSegmentRecord(
                        id=segment_id,
                        live_task_id=live_task_id,
                        sequence=_sequence_from_path(path),
                        video_path=str(path),
                        completed=False,
                        created_at=now,
                    )
                )
                payloads.append(
                    ProcessSegmentPayload(
                        segment_id=segment_id,
                        product_context=product_context,
                        task_context=task_context,
                    )
                )
            session.commit()
        return payloads

    @staticmethod
    def _load_existing_paths(
        *,
        session: Session,
        live_task_id: str,
        paths: list[Path],
    ) -> set[str]:
        path_values = {str(path) for path in paths}
        if not path_values:
            return set()
        records = session.scalars(
            select(LiveSegmentRecord.video_path).where(
                LiveSegmentRecord.live_task_id == live_task_id,
                LiveSegmentRecord.video_path.in_(path_values),
            )
        ).all()
        return set(records)


def _sequence_from_path(path: Path) -> int:
    """Extract the numeric ffmpeg segment sequence from the file name."""
    suffix = path.stem.rsplit("_", maxsplit=1)[-1]
    if not suffix.isdigit():
        return 0
    return int(suffix)
