"""SQLAdmin views for worker nodes."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView
from starlette.requests import Request

from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord


class WorkerNodeAdmin(ModelView, model=WorkerNodeRecord):
    """Manage remote worker nodes."""

    name_plural = "Worker Nodes"
    form_columns: ClassVar[list[str]] = [
        "id",
        "queue_name",
        "supported_platforms",
        "max_browser_sessions",
        "active_browser_sessions",
        "online",
        "last_heartbeat_at",
    ]
    column_list: ClassVar[list[str]] = [
        "id",
        "queue_name",
        "supported_platforms",
        "max_browser_sessions",
        "active_browser_sessions",
        "online",
        "last_heartbeat_at",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "queue_name"]

    async def on_model_change(
        self,
        data: dict[str, object],
        model: object,
        is_created: bool,
        request: Request,
    ) -> None:
        """Fill safe defaults for worker nodes created from SQLAdmin."""
        if not is_created or not isinstance(model, WorkerNodeRecord):
            return
        if not _has_text(model.queue_name) and _has_text(model.id):
            model.queue_name = f"node.{model.id}.browser"
        if not model.supported_platforms:
            model.supported_platforms = ["xhs"]
        if model.max_browser_sessions is None:
            model.max_browser_sessions = 1
        if model.active_browser_sessions is None:
            model.active_browser_sessions = 0
        if model.online is None:
            model.online = True


def _has_text(value: object) -> bool:
    """Return whether a value contains non-whitespace text."""
    return isinstance(value, str) and bool(value.strip())
