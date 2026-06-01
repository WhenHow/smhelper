from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.live.domain.policies.shutdown_policy import (
    CloseAction,
    LiveTaskShutdownPolicy,
)


def test_shutdown_policy_closes_waiting_sessions_immediately() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    session = AccountLiveSession(
        id="session-1",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.WAITING,
    )

    decisions = LiveTaskShutdownPolicy().plan_closures(sessions=[session], now=now)

    assert decisions[0].session_id == "session-1"
    assert decisions[0].action is CloseAction.DISPATCH_CLOSE
    assert decisions[0].reason == "live_ended"


def test_shutdown_policy_gives_sending_sessions_a_grace_period() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    session = AccountLiveSession(
        id="session-1",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.SENDING,
        send_started_at=now - timedelta(seconds=10),
    )

    decisions = LiveTaskShutdownPolicy(grace_period_seconds=30).plan_closures(
        sessions=[session],
        now=now,
    )

    assert decisions[0].action is CloseAction.WAIT_FOR_SENDING
    assert decisions[0].reason == "send_grace_period"


def test_shutdown_policy_forces_close_after_sending_grace_period_expires() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    session = AccountLiveSession(
        id="session-1",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.SENDING,
        send_started_at=now - timedelta(seconds=31),
    )

    decisions = LiveTaskShutdownPolicy(grace_period_seconds=30).plan_closures(
        sessions=[session],
        now=now,
    )

    assert decisions[0].action is CloseAction.FORCE_CLOSE
    assert decisions[0].reason == "shutdown_timeout"
