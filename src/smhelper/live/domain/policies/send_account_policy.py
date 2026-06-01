"""Policy for selecting a waiting account session to send a message."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from random import Random

from smhelper.core.exceptions import SmHelperError
from smhelper.live.domain.account_live_session import AccountLiveSession


class NoWaitingSessionAvailable(SmHelperError):
    """Raised when no waiting account session can send a message."""


@dataclass(slots=True)
class SendAccountPolicy:
    """Selects a waiting session with weighted randomness.

    The weight favors sessions that have been idle longer without becoming a
    strict round-robin. This keeps usage spread out while preserving randomness.
    """

    rng: Random = field(default_factory=Random)

    def select_session(
        self,
        *,
        sessions: Iterable[AccountLiveSession],
        now: datetime,
    ) -> AccountLiveSession:
        """Choose a waiting session that is not cooling down."""
        candidates = [
            session
            for session in sessions
            if session.is_waiting_to_send and not session.is_in_cooldown(now)
        ]
        if not candidates:
            raise NoWaitingSessionAvailable(
                "No waiting account live session is available"
            )

        weights = [self._weight(session=session, now=now) for session in candidates]
        return self.rng.choices(candidates, weights=weights, k=1)[0]

    @staticmethod
    def _weight(*, session: AccountLiveSession, now: datetime) -> float:
        if session.last_send_at is None:
            return 31.0
        idle_seconds = max((now - session.last_send_at).total_seconds(), 0.0)
        return 1.0 + min(idle_seconds / 60.0, 30.0)
