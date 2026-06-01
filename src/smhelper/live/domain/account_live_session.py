"""Account live-room session domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AccountLiveSessionStatus(str, Enum):
    """Lifecycle status of an account browser session inside a live room."""

    PLANNED = "planned"
    STARTING = "starting"
    WAITING = "waiting"
    SENDING = "sending"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"
    LOST = "lost"


ACTIVE_SESSION_STATUSES = frozenset(
    {
        AccountLiveSessionStatus.PLANNED,
        AccountLiveSessionStatus.STARTING,
        AccountLiveSessionStatus.WAITING,
        AccountLiveSessionStatus.SENDING,
        AccountLiveSessionStatus.CLOSING,
    }
)
RESTARTABLE_SESSION_STATUSES = frozenset(
    {
        AccountLiveSessionStatus.FAILED,
        AccountLiveSessionStatus.LOST,
    }
)


@dataclass(frozen=True, slots=True)
class AccountLiveSession:
    """A browser session for one account in one live task."""

    id: str
    live_task_id: str
    platform: str
    room_url: str
    account_id: str
    node_id: str
    status: AccountLiveSessionStatus
    opened_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_send_at: datetime | None = None
    failure_reason: str | None = None
    closed_at: datetime | None = None
    restart_count: int = 0
    cooldown_until: datetime | None = None
    send_started_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Return whether the session still occupies the account/live-task slot."""
        return self.status in ACTIVE_SESSION_STATUSES

    @property
    def is_waiting_to_send(self) -> bool:
        """Return whether the session can be considered for sending a message."""
        return self.status is AccountLiveSessionStatus.WAITING

    def is_in_cooldown(self, now: datetime) -> bool:
        """Return whether successful-send cooldown is still active."""
        return self.cooldown_until is not None and self.cooldown_until > now

    def can_auto_restart(self, *, max_restarts: int) -> bool:
        """Return whether this abnormal terminal session may be rebuilt."""
        return (
            self.status in RESTARTABLE_SESSION_STATUSES
            and self.restart_count < max_restarts
        )
