"""SQLAlchemy-backed live-task observer orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy.orm import Session, sessionmaker

from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.live_task_starter import (
    LiveTaskStartResult,
)
from smhelper.live.application.ports.live_stream_observer import (
    LiveStreamObservation,
    LiveStreamObservationSessionFactory,
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


class LiveTaskSegmentScheduler(Protocol):
    """Schedules completed segment processing for a live task."""

    def schedule_live_task_segments(
        self,
        *,
        live_task_id: str,
        include_last: bool = False,
    ) -> list[str]:
        """Schedule completed media segments for one live task."""


class LiveTaskSessionHealthChecker(Protocol):
    """Schedules worker-side health checks for active account sessions."""

    def check_live_task_sessions(self, *, live_task_id: str) -> list[str]:
        """Schedule health checks for account sessions of one live task."""


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
    segment_scheduler: LiveTaskSegmentScheduler | None = None
    session_health_checker: LiveTaskSessionHealthChecker | None = None

    def run_once(self, *, live_task_id: str) -> LiveTaskObservationRunResult | None:
        """Observe the task room once and start or update the task state."""
        room_url = self._load_room_url(live_task_id=live_task_id)
        if room_url is None:
            return None
        observation = self.observer.observe(room_url=room_url)
        return self._handle_observation(
            live_task_id=live_task_id,
            observation=observation,
        )

    def run_until_finished(
        self,
        *,
        live_task_id: str,
        observation_interval_ms: int = 5_000,
        max_checks: int | None = None,
    ) -> LiveTaskObservationRunResult | None:
        """Keep one observer page open until the live task ends or checks stop."""
        room_url = self._load_room_url(live_task_id=live_task_id)
        if room_url is None:
            return None

        observation_session = cast(
            LiveStreamObservationSessionFactory, self.observer
        ).open_session(room_url=room_url)
        checks = 0
        last_result: LiveTaskObservationRunResult | None = None
        try:
            while max_checks is None or checks < max_checks:
                observation = observation_session.observe()
                last_result = self._handle_observation(
                    live_task_id=live_task_id,
                    observation=observation,
                )
                checks += 1
                if observation.status is LiveStreamObservationStatus.LIVE:
                    self._schedule_segments(
                        live_task_id=live_task_id,
                        include_last=False,
                    )
                    self._check_sessions(live_task_id=live_task_id)
                if observation.status is LiveStreamObservationStatus.NOT_LIVE:
                    self._schedule_segments(
                        live_task_id=live_task_id,
                        include_last=True,
                    )
                    return last_result
                if max_checks is not None and checks >= max_checks:
                    return last_result
                observation_session.wait(observation_interval_ms)
            return last_result
        finally:
            observation_session.close()

    def _handle_observation(
        self,
        *,
        live_task_id: str,
        observation: LiveStreamObservation,
    ) -> LiveTaskObservationRunResult:
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

    def _load_room_url(self, *, live_task_id: str) -> str | None:
        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if live_task is None:
                return None
            return live_task.room_url

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

    def _schedule_segments(
        self,
        *,
        live_task_id: str,
        include_last: bool,
    ) -> None:
        if self.segment_scheduler is None:
            return
        self.segment_scheduler.schedule_live_task_segments(
            live_task_id=live_task_id,
            include_last=include_last,
        )

    def _check_sessions(self, *, live_task_id: str) -> None:
        if self.session_health_checker is None:
            return
        self.session_health_checker.check_live_task_sessions(live_task_id=live_task_id)

    def _record_failure(self, *, live_task_id: str, failure_reason: str) -> None:
        with self.session_factory() as session:
            live_task = session.get(LiveTaskRecord, live_task_id)
            if live_task is None:
                return
            live_task.failure_reason = failure_reason
            session.commit()
