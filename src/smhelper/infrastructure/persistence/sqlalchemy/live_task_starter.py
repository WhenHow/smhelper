"""SQLAlchemy-backed live-task startup orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.clock import Clock
from smhelper.infrastructure.media.ffmpeg.runner import BackgroundProcessStarter
from smhelper.infrastructure.media.ffmpeg.segment_recorder import (
    FFmpegSegmentRecorder,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord

STARTABLE_LIVE_TASK_STATUSES = frozenset({"pending", "created", "ready"})


class AccountEntryPlanner(Protocol):
    """Plans and dispatches account entry tasks for a live task."""

    def plan_and_dispatch(self, *, live_task_id: str) -> list[str]:
        """Create account live-room entry tasks."""


@dataclass(frozen=True, slots=True)
class LiveTaskStartResult:
    """Result of starting a live task's center-side runtime."""

    live_task_id: str
    output_dir: Path
    entry_session_ids: list[str]


@dataclass(frozen=True, slots=True)
class SqlAlchemyLiveTaskStarter:
    """Persist LiveTask startup state, start recording and schedule entries."""

    session_factory: sessionmaker[Session]
    clock: Clock
    process_starter: BackgroundProcessStarter
    account_entry_planner: AccountEntryPlanner
    media_root: Path
    ffmpeg_path: str

    def start_live_task(
        self,
        *,
        live_task_id: str,
        stream_url: str,
    ) -> LiveTaskStartResult | None:
        """Start recording for a discovered stream and dispatch account entries."""
        now = self.clock.now()
        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if (
                live_task is None
                or live_task.status not in STARTABLE_LIVE_TASK_STATUSES
            ):
                return None

            output_dir = self.media_root / live_task.id
            output_dir.mkdir(parents=True, exist_ok=True)
            command = FFmpegSegmentRecorder(
                ffmpeg_path=self.ffmpeg_path,
                stream_url=stream_url,
                output_dir=output_dir,
                segment_time_seconds=live_task.segment_time_seconds,
            ).build_command()
            self.process_starter.start(command)

            live_task.status = "running"
            live_task.stream_url = stream_url
            live_task.started_at = now
            session.commit()

        entry_session_ids = self.account_entry_planner.plan_and_dispatch(
            live_task_id=live_task_id,
        )
        return LiveTaskStartResult(
            live_task_id=live_task_id,
            output_dir=output_dir,
            entry_session_ids=entry_session_ids,
        )
