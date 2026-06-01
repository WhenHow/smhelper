"""SQLAdmin views for live tasks."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView

from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord


class LiveTaskAdmin(ModelView, model=LiveTaskRecord):
    """View live task runtime state."""

    name_plural = "Live Tasks"
    column_list: ClassVar[list[str]] = [
        "id",
        "platform",
        "room_url",
        "status",
        "stream_url",
        "segment_time_seconds",
        "created_at",
        "started_at",
        "ended_at",
        "failure_reason",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "room_url"]
