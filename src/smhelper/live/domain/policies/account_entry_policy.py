"""Policy that prevents duplicate account sessions in the same live task."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from smhelper.core.exceptions import SmHelperError
from smhelper.live.domain.account_live_session import AccountLiveSession


class DuplicateActiveSession(SmHelperError):
    """Raised when an account already has an active session in a live task."""


@dataclass(frozen=True, slots=True)
class AccountEntryPolicy:
    """Guards creation of account live sessions."""

    def ensure_can_create_session(
        self,
        *,
        live_task_id: str,
        account_id: str,
        existing_sessions: Iterable[AccountLiveSession],
    ) -> None:
        """Raise if the account already has an active session for the task."""
        duplicate = next(
            (
                session
                for session in existing_sessions
                if session.live_task_id == live_task_id
                and session.account_id == account_id
                and session.is_active
            ),
            None,
        )
        if duplicate is not None:
            raise DuplicateActiveSession(
                f"Account {account_id!r} already has active session {duplicate.id!r}"
            )
