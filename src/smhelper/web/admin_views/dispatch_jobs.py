"""SQLAdmin views for dispatch jobs and send attempts."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView

from smhelper.infrastructure.persistence.sqlalchemy.live import (
    DispatchJobRecord,
    SendAttemptRecord,
)


class DispatchJobAdmin(ModelView, model=DispatchJobRecord):
    """View approved-question dispatch jobs."""

    name_plural = "Dispatch Jobs"
    can_create = False
    can_edit = False
    can_delete = False
    column_list: ClassVar[list[str]] = [
        "id",
        "candidate_question_id",
        "live_task_id",
        "account_live_session_id",
        "account_id",
        "final_text",
        "status",
        "created_at",
        "started_at",
        "finished_at",
        "failure_reason",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "candidate_question_id"]


class SendAttemptAdmin(ModelView, model=SendAttemptRecord):
    """View worker-side send attempt audit rows."""

    name_plural = "Send Attempts"
    can_create = False
    can_edit = False
    can_delete = False
    column_list: ClassVar[list[str]] = [
        "id",
        "dispatch_job_id",
        "account_live_session_id",
        "account_id",
        "status",
        "success_detection",
        "attempted_at",
        "failure_reason",
        "page_snapshot_path",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "dispatch_job_id"]
