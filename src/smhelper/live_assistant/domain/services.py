"""Domain services and policies for live assistant scheduling."""

from __future__ import annotations

from dataclasses import dataclass

from smhelper.live_assistant.domain.exceptions import (
    AccountNotAvailable,
    PlatformMismatch,
    SessionNotReady,
)
from smhelper.live_assistant.domain.models import (
    Account,
    LiveRoom,
    LiveRoomSession,
    SessionStatus,
)


@dataclass(frozen=True, slots=True)
class AccountSchedulingService:
    """Rules for choosing whether an account may enter a room."""

    def ensure_can_enter(self, account: Account, room: LiveRoom) -> None:
        """Raise when the account is not eligible for the target room."""
        if not account.enabled:
            raise AccountNotAvailable(f"account {account.id!r} is disabled")
        if account.platform != room.platform:
            raise PlatformMismatch(
                f"account {account.id!r} is for {account.platform!r}, "
                f"not {room.platform!r}"
            )


@dataclass(frozen=True, slots=True)
class CommentDispatchPolicy:
    """Rules for sending comments from live room sessions."""

    def ensure_can_send(self, session: LiveRoomSession) -> None:
        """Raise when the session cannot dispatch comments."""
        if session.status is not SessionStatus.WAITING:
            raise SessionNotReady(
                f"session {session.id!r} must be waiting before sending"
            )
