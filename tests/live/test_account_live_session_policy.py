from __future__ import annotations

from datetime import UTC, datetime

import pytest

from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.live.domain.policies.account_entry_policy import (
    AccountEntryPolicy,
    DuplicateActiveSession,
)


def test_account_live_session_marks_only_runtime_states_as_active() -> None:
    active_statuses = {
        AccountLiveSessionStatus.PLANNED,
        AccountLiveSessionStatus.STARTING,
        AccountLiveSessionStatus.WAITING,
        AccountLiveSessionStatus.SENDING,
        AccountLiveSessionStatus.CLOSING,
    }

    for status in AccountLiveSessionStatus:
        session = AccountLiveSession(
            id=f"session-{status.value}",
            live_task_id="live-1",
            platform="xhs",
            room_url="https://example.com/live/1",
            account_id="account-1",
            node_id="node-a",
            status=status,
        )

        assert session.is_active is (status in active_statuses)


def test_account_entry_policy_rejects_duplicate_active_session() -> None:
    sessions = [
        AccountLiveSession(
            id="session-1",
            live_task_id="live-1",
            platform="xhs",
            room_url="https://example.com/live/1",
            account_id="account-1",
            node_id="node-a",
            status=AccountLiveSessionStatus.WAITING,
        )
    ]

    with pytest.raises(DuplicateActiveSession, match="account-1"):
        AccountEntryPolicy().ensure_can_create_session(
            live_task_id="live-1",
            account_id="account-1",
            existing_sessions=sessions,
        )


def test_account_entry_policy_allows_new_session_after_old_one_is_terminal() -> None:
    sessions = [
        AccountLiveSession(
            id="session-1",
            live_task_id="live-1",
            platform="xhs",
            room_url="https://example.com/live/1",
            account_id="account-1",
            node_id="node-a",
            status=AccountLiveSessionStatus.CLOSED,
            closed_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        )
    ]

    AccountEntryPolicy().ensure_can_create_session(
        live_task_id="live-1",
        account_id="account-1",
        existing_sessions=sessions,
    )


def test_account_live_session_restart_limit_requires_old_session_to_be_terminal() -> (
    None
):
    failed = AccountLiveSession(
        id="session-1",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.FAILED,
        restart_count=1,
    )
    waiting = AccountLiveSession(
        id="session-2",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.WAITING,
        restart_count=1,
    )
    exhausted = AccountLiveSession(
        id="session-3",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.FAILED,
        restart_count=2,
    )

    assert failed.can_auto_restart(max_restarts=2) is True
    assert waiting.can_auto_restart(max_restarts=2) is False
    assert exhausted.can_auto_restart(max_restarts=2) is False
