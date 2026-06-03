"""SQLAdmin views for live tasks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Protocol

from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse

from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ObserveLiveTaskPayload,
)


class LiveTaskObserverPublisher(Protocol):
    """Publisher used by the SQLAdmin live-task observe action."""

    def observe_live_task(
        self,
        *,
        queue_name: str,
        payload: ObserveLiveTaskPayload,
    ) -> None:
        """Publish one live-task observation task."""


class LiveTaskAdmin(ModelView, model=LiveTaskRecord):
    """View live task runtime state."""

    observer_publisher: ClassVar[LiveTaskObserverPublisher | None] = None
    center_queue_name: ClassVar[str] = "center.live"
    name_plural = "Live Tasks"
    form_columns: ClassVar[list[str]] = [
        "id",
        "title",
        "platform",
        "room_url",
        "status",
        "product_context",
        "task_context",
        "segment_time_seconds",
    ]
    column_list: ClassVar[list[str]] = [
        "id",
        "title",
        "platform",
        "room_url",
        "status",
        "stream_url",
        "product_context",
        "task_context",
        "segment_time_seconds",
        "created_at",
        "started_at",
        "ended_at",
        "failure_reason",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "room_url"]

    async def on_model_change(
        self,
        data: dict[str, object],
        model: object,
        is_created: bool,
        request: Request,
    ) -> None:
        """Fill defaults needed for manually created first-phase live tasks."""
        if not is_created or not isinstance(model, LiveTaskRecord):
            return
        if not _has_text(model.platform):
            model.platform = "xhs"
        if not _has_text(model.status):
            model.status = "pending"
        if model.product_context is None:
            model.product_context = ""
        if model.task_context is None:
            model.task_context = ""
        if model.segment_time_seconds is None:
            model.segment_time_seconds = 60
        if model.created_at is None:
            model.created_at = datetime.now(UTC)

    @action(
        name="observe",
        label="Observe",
        confirmation_message="Observe selected live tasks?",
    )
    async def observe_live_tasks(self, request: Request) -> RedirectResponse:
        """Publish observation tasks for selected LiveTask rows."""
        raw_pks = request.query_params.get("pks", "")
        live_task_ids = [
            live_task_id for live_task_id in raw_pks.split(",") if live_task_id
        ]
        if live_task_ids:
            if self.observer_publisher is None:
                raise RuntimeError("live task observer publisher is not configured")
            for live_task_id in live_task_ids:
                self.observer_publisher.observe_live_task(
                    queue_name=self.center_queue_name,
                    payload=ObserveLiveTaskPayload(live_task_id=live_task_id),
                )
        return RedirectResponse(
            request.headers.get("referer", "/admin/livetask/list"),
            status_code=302,
        )


def _has_text(value: object) -> bool:
    """Return whether a value contains non-whitespace text."""
    return isinstance(value, str) and bool(value.strip())
