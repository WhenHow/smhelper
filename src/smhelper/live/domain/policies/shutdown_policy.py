"""Policy for closing account live sessions after a live task ends."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)


class CloseAction(str, Enum):
    """Center-side close decision for a remote account live session."""

    DISPATCH_CLOSE = "dispatch_close"
    WAIT_FOR_SENDING = "wait_for_sending"
    FORCE_CLOSE = "force_close"


@dataclass(frozen=True, slots=True)
class CloseDecision:
    """Close action planned for one account live session."""

    session_id: str
    node_id: str
    action: CloseAction
    reason: str


@dataclass(frozen=True, slots=True)
class LiveTaskShutdownPolicy:
    """Plans session close actions when the center decides a live task has ended."""

    grace_period_seconds: int = 30

    def plan_closures(
        self,
        *,
        sessions: Iterable[AccountLiveSession],
        now: datetime,
    ) -> list[CloseDecision]:
        """Return close decisions for active sessions."""
        decisions: list[CloseDecision] = []
        for session in sessions:
            if not session.is_active:
                continue
            decisions.append(self._decision_for(session=session, now=now))
        return decisions

    def _decision_for(
        self,
        *,
        session: AccountLiveSession,
        now: datetime,
    ) -> CloseDecision:
        if session.status is not AccountLiveSessionStatus.SENDING:
            return CloseDecision(
                session_id=session.id,
                node_id=session.node_id,
                action=CloseAction.DISPATCH_CLOSE,
                reason="live_ended",
            )
        if session.send_started_at is None:
            return CloseDecision(
                session_id=session.id,
                node_id=session.node_id,
                action=CloseAction.FORCE_CLOSE,
                reason="shutdown_timeout",
            )

        elapsed_seconds = (now - session.send_started_at).total_seconds()
        if elapsed_seconds <= self.grace_period_seconds:
            return CloseDecision(
                session_id=session.id,
                node_id=session.node_id,
                action=CloseAction.WAIT_FOR_SENDING,
                reason="send_grace_period",
            )
        return CloseDecision(
            session_id=session.id,
            node_id=session.node_id,
            action=CloseAction.FORCE_CLOSE,
            reason="shutdown_timeout",
        )
