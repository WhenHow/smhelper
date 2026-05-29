"""Live assistant domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from smhelper.live_assistant.domain.exceptions import (
    InvalidCommentMessage,
    InvalidLiveRoom,
)


class SessionStatus(str, Enum):
    """Status of an account's live room session."""

    WAITING = "waiting"
    ENTER_FAILED = "enter_failed"


class CommentDispatchStatus(str, Enum):
    """Status of a comment dispatch attempt."""

    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Account:
    """Authorized account that may enter a platform live room."""

    id: str
    platform: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AccountAuthProfile:
    """Persistent browser profile metadata for an authorized account."""

    account_id: str
    platform: str
    profile_dir: Path
    login_url: str
    last_login_at: datetime
    status: str
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LiveRoom:
    """Target live room for account scheduling."""

    url: str
    platform: str

    def __post_init__(self) -> None:
        """Validate the room value object."""
        if not self.url.strip():
            raise InvalidLiveRoom("live room url must not be blank")
        if not self.platform.strip():
            raise InvalidLiveRoom("live room platform must not be blank")


@dataclass(frozen=True, slots=True)
class CommentMessage:
    """Operator-approved comment text to send in a live room."""

    text: str

    def __post_init__(self) -> None:
        """Normalize and validate comment text."""
        normalized = self.text.strip()
        if not normalized:
            raise InvalidCommentMessage("comment text must not be blank")
        object.__setattr__(self, "text", normalized)


@dataclass(frozen=True, slots=True)
class LiveRoomSession:
    """Session representing an account waiting in a live room."""

    id: str
    account_id: str
    room_url: str
    platform: str
    status: SessionStatus
    entered_at: datetime
    failure_reason: str | None = None

    @classmethod
    def waiting(
        cls,
        id: str,
        account_id: str,
        room_url: str,
        platform: str,
        entered_at: datetime,
    ) -> LiveRoomSession:
        """Create a successful waiting session."""
        return cls(
            id=id,
            account_id=account_id,
            room_url=room_url,
            platform=platform,
            status=SessionStatus.WAITING,
            entered_at=entered_at,
        )

    @classmethod
    def enter_failed(
        cls,
        id: str,
        account_id: str,
        room_url: str,
        platform: str,
        entered_at: datetime,
        failure_reason: str,
    ) -> LiveRoomSession:
        """Create a failed enter-room session record."""
        return cls(
            id=id,
            account_id=account_id,
            room_url=room_url,
            platform=platform,
            status=SessionStatus.ENTER_FAILED,
            entered_at=entered_at,
            failure_reason=failure_reason,
        )


@dataclass(frozen=True, slots=True)
class CommentDispatch:
    """Persistent audit record for one comment dispatch attempt."""

    id: str
    session_id: str
    account_id: str
    text: str
    status: CommentDispatchStatus
    sent_at: datetime
    failure_reason: str | None = None
