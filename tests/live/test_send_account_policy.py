from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random

import pytest

from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.live.domain.policies.send_account_policy import (
    NoWaitingSessionAvailable,
    SendAccountPolicy,
)


def test_send_account_policy_selects_only_waiting_usable_sessions() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    sessions = [
        AccountLiveSession(
            id="session-sending",
            live_task_id="live-1",
            platform="xhs",
            room_url="https://example.com/live/1",
            account_id="account-sending",
            node_id="node-a",
            status=AccountLiveSessionStatus.SENDING,
        ),
        AccountLiveSession(
            id="session-cooldown",
            live_task_id="live-1",
            platform="xhs",
            room_url="https://example.com/live/1",
            account_id="account-cooldown",
            node_id="node-a",
            status=AccountLiveSessionStatus.WAITING,
            cooldown_until=now + timedelta(minutes=5),
        ),
        AccountLiveSession(
            id="session-ready",
            live_task_id="live-1",
            platform="xhs",
            room_url="https://example.com/live/1",
            account_id="account-ready",
            node_id="node-a",
            status=AccountLiveSessionStatus.WAITING,
            last_send_at=now - timedelta(hours=2),
        ),
    ]

    selected = SendAccountPolicy(rng=Random(7)).select_session(
        sessions=sessions, now=now
    )

    assert selected.id == "session-ready"


def test_send_account_policy_biases_toward_more_idle_sessions_without_round_robin() -> (
    None
):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    recently_used = AccountLiveSession(
        id="session-recent",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-recent",
        node_id="node-a",
        status=AccountLiveSessionStatus.WAITING,
        last_send_at=now - timedelta(seconds=30),
    )
    idle = AccountLiveSession(
        id="session-idle",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-idle",
        node_id="node-a",
        status=AccountLiveSessionStatus.WAITING,
        last_send_at=now - timedelta(minutes=30),
    )

    selections = [
        SendAccountPolicy(rng=Random(seed)).select_session(
            sessions=[recently_used, idle],
            now=now,
        )
        for seed in range(50)
    ]

    assert sum(session.id == "session-idle" for session in selections) > sum(
        session.id == "session-recent" for session in selections
    )
    assert {session.id for session in selections} == {"session-recent", "session-idle"}


def test_send_account_policy_raises_when_no_waiting_session_is_available() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    sessions = [
        AccountLiveSession(
            id="session-closing",
            live_task_id="live-1",
            platform="xhs",
            room_url="https://example.com/live/1",
            account_id="account-1",
            node_id="node-a",
            status=AccountLiveSessionStatus.CLOSING,
        )
    ]

    with pytest.raises(NoWaitingSessionAvailable):
        SendAccountPolicy(rng=Random(1)).select_session(sessions=sessions, now=now)
