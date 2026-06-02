"""Celery publishers for browser-node tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from smhelper.infrastructure.task_queue.celery.tasks import (
    CLOSE_SESSION_TASK,
    ENTER_LIVE_ROOM_TASK,
    SEND_COMMENT_TASK,
)


class CeleryTaskSender(Protocol):
    """Subset of Celery used by the task publisher."""

    def send_task(
        self,
        name: str,
        *,
        kwargs: dict[str, str],
        queue: str,
        countdown: int | None = None,
    ) -> object:
        """Send a task to a named queue."""


@dataclass(frozen=True, slots=True)
class EnterLiveRoomPayload:
    """Payload for asking a node to open an account live-room session."""

    session_id: str
    account_id: str
    live_task_id: str
    room_url: str
    platform: str

    def to_kwargs(self) -> dict[str, str]:
        """Serialize the payload for Celery JSON transport."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SendCommentPayload:
    """Payload for asking a node to send approved text in an existing session."""

    dispatch_job_id: str
    session_id: str
    account_id: str
    final_text: str

    def to_kwargs(self) -> dict[str, str]:
        """Serialize the payload for Celery JSON transport."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CloseSessionPayload:
    """Payload for asking a node to close an account live-room session."""

    session_id: str
    reason: str

    def to_kwargs(self) -> dict[str, str]:
        """Serialize the payload for Celery JSON transport."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BrowserTaskPublisher:
    """Publishes browser automation tasks to node-specific Celery queues."""

    celery_app: CeleryTaskSender

    def enter_live_room(
        self,
        *,
        queue_name: str,
        payload: EnterLiveRoomPayload,
        countdown_seconds: int | None = None,
    ) -> None:
        """Publish an enter-live-room task."""
        self.celery_app.send_task(
            ENTER_LIVE_ROOM_TASK,
            kwargs=payload.to_kwargs(),
            queue=queue_name,
            countdown=countdown_seconds,
        )

    def send_comment(
        self,
        *,
        queue_name: str,
        payload: SendCommentPayload,
    ) -> None:
        """Publish a send-comment task."""
        self.celery_app.send_task(
            SEND_COMMENT_TASK,
            kwargs=payload.to_kwargs(),
            queue=queue_name,
        )

    def close_session(
        self,
        *,
        queue_name: str,
        payload: CloseSessionPayload,
    ) -> None:
        """Publish a close-session task."""
        self.celery_app.send_task(
            CLOSE_SESSION_TASK,
            kwargs=payload.to_kwargs(),
            queue=queue_name,
        )
