"""SQLAdmin views for live segment artifacts and ASR transcripts."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView

from smhelper.infrastructure.persistence.sqlalchemy.live import (
    LiveSegmentRecord,
    TranscriptRecord,
)


class LiveSegmentAdmin(ModelView, model=LiveSegmentRecord):
    """View persisted media segments and generated artifact paths."""

    name_plural = "Live Segments"
    can_create = False
    column_list: ClassVar[list[str]] = [
        "id",
        "live_task_id",
        "sequence",
        "video_path",
        "first_frame_path",
        "last_frame_path",
        "audio_path",
        "completed",
        "created_at",
        "completed_at",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "live_task_id"]


class TranscriptAdmin(ModelView, model=TranscriptRecord):
    """View ASR transcript results for completed live segments."""

    name_plural = "Transcripts"
    can_create = False
    column_list: ClassVar[list[str]] = [
        "id",
        "live_task_id",
        "segment_id",
        "provider_name",
        "text",
        "raw_response",
        "status",
        "transcribed_at",
        "failure_reason",
    ]
    column_searchable_list: ClassVar[list[str]] = [
        "id",
        "live_task_id",
        "segment_id",
    ]
