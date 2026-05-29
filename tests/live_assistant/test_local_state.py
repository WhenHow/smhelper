from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from smhelper.live_assistant.domain.models import Account, AccountAuthProfile
from smhelper.live_assistant.infrastructure.local_state import LocalStateUnitOfWork


def test_local_state_unit_of_work_persists_accounts_and_auth_profiles(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.json"
    logged_in_at = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    first = LocalStateUnitOfWork(state_path)
    first.accounts.add(Account(id="account-1", platform="xhs"))
    first.auth_profiles.add(
        AccountAuthProfile(
            account_id="account-1",
            platform="xhs",
            profile_dir=tmp_path / "profiles" / "xhs" / "account-1",
            login_url="https://www.xiaohongshu.com/explore",
            last_login_at=logged_in_at,
            status="saved",
        )
    )

    first.commit()
    second = LocalStateUnitOfWork(state_path)

    assert second.accounts.get("account-1") == Account(id="account-1", platform="xhs")
    profile = second.auth_profiles.get(account_id="account-1", platform="xhs")
    assert profile is not None
    assert profile.profile_dir == tmp_path / "profiles" / "xhs" / "account-1"
    assert profile.last_login_at == logged_in_at
    assert profile.status == "saved"
