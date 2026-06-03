"""Celery task registration for worker-node browser operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from smhelper.infrastructure.task_queue.celery.publisher import (
    CheckSessionPayload,
    CloseSessionPayload,
    EnterLiveRoomPayload,
    SendCommentPayload,
)
from smhelper.infrastructure.task_queue.celery.tasks import (
    CHECK_SESSION_TASK,
    CLOSE_SESSION_TASK,
    ENTER_LIVE_ROOM_TASK,
    SEND_COMMENT_TASK,
)


TaskFunction = Callable[..., None]
TaskDecorator = Callable[[TaskFunction], TaskFunction]


class CeleryTaskRegistry(Protocol):
    """Subset of Celery needed to register named tasks."""

    def task(self, *, name: str) -> TaskDecorator:
        """Decorate a function as a named Celery task."""


class NodeTaskHandler(Protocol):
    """Handler surface consumed by registered node tasks."""

    def enter_live_room(self, payload: EnterLiveRoomPayload) -> None:
        """Handle an enter-live-room task."""

    def send_comment(self, payload: SendCommentPayload) -> None:
        """Handle a send-comment task."""

    def check_session(self, payload: CheckSessionPayload) -> None:
        """Handle a session-health check task."""

    def close_session(self, payload: CloseSessionPayload) -> None:
        """Handle a close-session task."""


def register_node_browser_tasks(
    *,
    app: CeleryTaskRegistry,
    handler: NodeTaskHandler,
) -> None:
    """Register browser node Celery tasks and delegate to the provided handler."""

    @app.task(name=ENTER_LIVE_ROOM_TASK)
    def enter_live_room(
        *,
        session_id: str,
        account_id: str,
        live_task_id: str,
        room_url: str,
        platform: str,
    ) -> None:
        handler.enter_live_room(
            EnterLiveRoomPayload(
                session_id=session_id,
                account_id=account_id,
                live_task_id=live_task_id,
                room_url=room_url,
                platform=platform,
            )
        )

    @app.task(name=SEND_COMMENT_TASK)
    def send_comment(
        *,
        dispatch_job_id: str,
        session_id: str,
        account_id: str,
        final_text: str,
    ) -> None:
        handler.send_comment(
            SendCommentPayload(
                dispatch_job_id=dispatch_job_id,
                session_id=session_id,
                account_id=account_id,
                final_text=final_text,
            )
        )

    @app.task(name=CHECK_SESSION_TASK)
    def check_session(*, session_id: str) -> None:
        handler.check_session(CheckSessionPayload(session_id=session_id))

    @app.task(name=CLOSE_SESSION_TASK)
    def close_session(*, session_id: str, reason: str) -> None:
        handler.close_session(CloseSessionPayload(session_id=session_id, reason=reason))
