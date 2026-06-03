"""SQLAdmin views for accounts and auth-state metadata."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)


class PlatformAccountAdmin(ModelView, model=PlatformAccountRecord):
    """Manage platform accounts."""

    name_plural = "Platform Accounts"
    column_list: ClassVar[list[str]] = [
        "id",
        "platform",
        "display_name",
        "enabled",
        "daily_send_limit",
        "sends_today",
        "cooldown_until",
    ]
    column_searchable_list: ClassVar[list[str]] = ["id", "display_name"]


class AccountAuthStateAdmin(ModelView, model=AccountAuthStateRecord):
    """View auth-state metadata without exposing raw storage-state content."""

    name_plural = "Account Auth States"
    can_delete = False
    column_list: ClassVar[list[str]] = [
        "account_id",
        "platform",
        "status",
        "storage_state_path",
        "failure_reason",
        "updated_at",
    ]
    column_searchable_list: ClassVar[list[str]] = ["account_id", "storage_state_path"]
