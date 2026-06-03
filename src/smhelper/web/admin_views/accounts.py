"""SQLAdmin views for accounts and auth-state metadata."""

from __future__ import annotations

from typing import ClassVar

from sqladmin import ModelView
from starlette.requests import Request

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)


class PlatformAccountAdmin(ModelView, model=PlatformAccountRecord):
    """Manage platform accounts."""

    name_plural = "Platform Accounts"
    form_columns: ClassVar[list[str]] = [
        "id",
        "platform",
        "display_name",
        "enabled",
        "daily_send_limit",
        "sends_today",
        "cooldown_until",
    ]
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

    async def on_model_change(
        self,
        data: dict[str, object],
        model: object,
        is_created: bool,
        request: Request,
    ) -> None:
        """Fill safe development defaults for manually created accounts."""
        if not is_created or not isinstance(model, PlatformAccountRecord):
            return
        if not _has_text(model.platform):
            model.platform = "xhs"
        if model.enabled is None:
            model.enabled = True
        if model.daily_send_limit is None:
            model.daily_send_limit = 20
        if model.sends_today is None:
            model.sends_today = 0


class AccountAuthStateAdmin(ModelView, model=AccountAuthStateRecord):
    """View auth-state metadata without exposing raw storage-state content."""

    name_plural = "Account Auth States"
    can_delete = False
    form_columns: ClassVar[list[str]] = [
        "account_id",
        "platform",
        "status",
        "storage_state_path",
        "failure_reason",
        "updated_at",
    ]
    column_list: ClassVar[list[str]] = [
        "account_id",
        "platform",
        "status",
        "storage_state_path",
        "failure_reason",
        "updated_at",
    ]
    column_searchable_list: ClassVar[list[str]] = ["account_id", "storage_state_path"]

    async def on_model_change(
        self,
        data: dict[str, object],
        model: object,
        is_created: bool,
        request: Request,
    ) -> None:
        """Fill defaults for auth-state metadata rows created in SQLAdmin."""
        if not is_created or not isinstance(model, AccountAuthStateRecord):
            return
        if not _has_text(model.platform):
            model.platform = "xhs"
        if not _has_text(model.status):
            model.status = "valid"


def _has_text(value: object) -> bool:
    """Return whether a value contains non-whitespace text."""
    return isinstance(value, str) and bool(value.strip())
