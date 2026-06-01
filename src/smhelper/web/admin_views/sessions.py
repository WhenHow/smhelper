"""SQLAdmin views for account live sessions."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView

from smhelper.infrastructure.persistence.sqlalchemy.live import AccountLiveSessionRecord


class AccountLiveSessionAdmin(ModelView, model=AccountLiveSessionRecord):
    """View account browser sessions in live rooms."""

    name_plural = "Account Live Sessions"
    can_create = False
    column_list: ClassVar[list[str]] = [
        "id",
        "live_task_id",
        "account_id",
        "node_id",
        "status",
        "last_heartbeat_at",
        "last_send_at",
        "failure_reason",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "account_id", "node_id"]
