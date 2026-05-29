"""Repository protocols owned by the live assistant domain."""

from __future__ import annotations

from typing import Protocol

from smhelper.live_assistant.domain.models import (
    Account,
    AccountAuthProfile,
    CommentDispatch,
    LiveRoomSession,
)


class AccountRepository(Protocol):
    """Stores authorized live assistant accounts."""

    def get(self, account_id: str) -> Account | None:
        """Return an account by ID."""

    def add(self, account: Account) -> None:
        """Store or replace an account."""


class AccountAuthProfileRepository(Protocol):
    """Stores persistent browser profile metadata for accounts."""

    def get(self, account_id: str, platform: str) -> AccountAuthProfile | None:
        """Return a profile by account and platform."""

    def add(self, profile: AccountAuthProfile) -> None:
        """Store or replace a profile."""


class LiveRoomSessionRepository(Protocol):
    """Stores live room session records."""

    def get(self, session_id: str) -> LiveRoomSession | None:
        """Return a session by ID."""

    def add(self, session: LiveRoomSession) -> None:
        """Store or replace a session."""


class CommentDispatchRepository(Protocol):
    """Stores comment dispatch audit records."""

    def get(self, dispatch_id: str) -> CommentDispatch | None:
        """Return a dispatch record by ID."""

    def add(self, dispatch: CommentDispatch) -> None:
        """Store or replace a dispatch record."""
