"""SQLAlchemy-backed live-task observer orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.live_task_starter import (
    LiveTaskStartResult,
)
from smhelper.live.application.ports.live_stream_observer import (
    LiveStreamObservation,
    LiveStreamObservationStatus,
    LiveStreamObserver,
)


class LiveTaskStarter(Protocol):
    """Starts a live task after a stream URL has been discovered."""

    def start_live_task(
        self,
        *,
        live_task_id: str,
        stream_url: str,
    ) -> LiveTaskStartResult | None:
        """Start the live task or return None when it is not startable."""


class LiveTaskTerminator(Protocol):
    """Terminates a live task and coordinates account-session shutdown."""

    def end_live_task(
        self,
        *,
        live_task_id: str,
        failure_reason: str | None = None,
    ) -> list[str]:
        """End the live task and close active sessions."""


@dataclass(frozen=True, slots=True)
class LiveTaskObservationRunResult:
    """Result of one center-side live-task observation attempt."""

    live_task_id: str
    status: LiveStreamObservationStatus
    stream_url: str | None
    start_result: LiveTaskStartResult | None


@dataclass(frozen=True, slots=True)
class SqlAlchemyLiveTaskObserverRunner:
    """Observe one LiveTask and advance center-side startup state."""

    session_factory: sessionmaker[Session]
    observer: LiveStreamObserver
    starter: LiveTaskStarter
    terminator: LiveTaskTerminator

    def run_once(self, *, live_task_id: str) -> LiveTaskObservationRunResult | None:
        """Observe the task room once and start or update the task state."""
        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if live_task is None:
                return None
            room_url = live_task.room_url

        observation = self.observer.observe(room_url=room_url)
        if observation.status is LiveStreamObservationStatus.LIVE:
            return self._handle_live(
                live_task_id=live_task_id,
                observation=observation,
            )
        if observation.status is LiveStreamObservationStatus.NOT_LIVE:
            self.terminator.end_live_task(
                live_task_id=live_task_id,
                failure_reason="live_not_active",
            )
        else:
            self._record_failure(
                live_task_id=live_task_id,
                failure_reason="live_status_unknown",
            )
        return LiveTaskObservationRunResult(
            live_task_id=live_task_id,
            status=observation.status,
            stream_url=observation.stream_url,
            start_result=None,
        )

    def _handle_live(
        self,
        *,
        live_task_id: str,
        observation: LiveStreamObservation,
    ) -> LiveTaskObservationRunResult:
        if observation.stream_url is None:
            self._record_failure(
                live_task_id=live_task_id,
                failure_reason="stream_url_not_found",
            )
            return LiveTaskObservationRunResult(
                live_task_id=live_task_id,
                status=observation.status,
                stream_url=None,
                start_result=None,
            )
        start_result = self.starter.start_live_task(
            live_task_id=live_task_id,
            stream_url=observation.stream_url,
        )
        return LiveTaskObservationRunResult(
            live_task_id=live_task_id,
            status=observation.status,
            stream_url=observation.stream_url,
            start_result=start_result,
        )

    def _record_failure(self, *, live_task_id: str, failure_reason: str) -> None:
        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if live_task is None:
                return
            live_task.failure_reason = failure_reason
            session.commit()
