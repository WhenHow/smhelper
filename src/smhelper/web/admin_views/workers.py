"""SQLAdmin views for worker nodes."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView

from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord


class WorkerNodeAdmin(ModelView, model=WorkerNodeRecord):
    """Manage remote worker nodes."""

    name_plural = "Worker Nodes"
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
