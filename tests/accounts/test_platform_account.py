from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smhelper.accounts.domain.account_auth_state import (
    AccountAuthState,
    AccountAuthStatus,
)
from smhelper.accounts.domain.account_node_binding import AccountNodeBinding
from smhelper.accounts.domain.platform_account import PlatformAccount


def test_platform_account_is_available_only_when_enabled_and_auth_is_valid() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    account = PlatformAccount(
        id="account-1",
        platform="xhs",
        display_name="Account 1",
        enabled=True,
        daily_send_limit=10,
        sends_today=0,
        cooldown_until=None,
    )
    valid_auth = AccountAuthState(
        account_id="account-1",
        platform="xhs",
        status=AccountAuthStatus.VALID,
        storage_state_path="data/auth/xhs/account-1/storage_state.json",
    )

    assert account.is_available(now=now, auth_state=valid_auth) is True
    assert account.disable().is_available(now=now, auth_state=valid_auth) is False
    assert (
        account.is_available(
            now=now,
            auth_state=valid_auth.mark_expired(reason="login expired"),
        )
        is False
    )


def test_platform_account_cooldown_and_daily_limit_make_it_unavailable() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    valid_auth = AccountAuthState(
        account_id="account-1",
        platform="xhs",
        status=AccountAuthStatus.VALID,
        storage_state_path="data/auth/xhs/account-1/storage_state.json",
    )

    cooling_down = PlatformAccount(
        id="account-1",
        platform="xhs",
        display_name="Account 1",
        enabled=True,
        daily_send_limit=10,
        sends_today=0,
        cooldown_until=now + timedelta(minutes=5),
    )
    at_limit = PlatformAccount(
        id="account-1",
        platform="xhs",
        display_name="Account 1",
        enabled=True,
        daily_send_limit=3,
        sends_today=3,
        cooldown_until=None,
    )

    assert cooling_down.is_available(now=now, auth_state=valid_auth) is False
    assert at_limit.is_available(now=now, auth_state=valid_auth) is False


def test_account_node_binding_allows_all_nodes_when_no_explicit_binding_exists() -> (
    None
):
    unrestricted = AccountNodeBinding(
        account_id="account-1", allowed_node_ids=frozenset()
    )
    restricted = AccountNodeBinding(
        account_id="account-1",
        allowed_node_ids=frozenset({"node-a", "node-b"}),
    )

    assert unrestricted.is_node_allowed("node-x") is True
    assert restricted.is_node_allowed("node-a") is True
    assert restricted.is_node_allowed("node-x") is False
