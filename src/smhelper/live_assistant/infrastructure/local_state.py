"""JSON-backed local state for CLI workflows."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TypedDict, cast

from smhelper.live_assistant.domain.models import (
    Account,
    AccountAuthProfile,
)
from smhelper.live_assistant.infrastructure.memory import (
    InMemoryCommentDispatchRepository,
    InMemoryLiveRoomSessionRepository,
)


class AccountRecord(TypedDict):
    """JSON shape for an account record."""

    id: str
    platform: str
    enabled: bool


class AuthProfileRecord(TypedDict):
    """JSON shape for an account auth profile record."""

    account_id: str
    platform: str
    profile_dir: str
    login_url: str
    last_login_at: str
    status: str
    failure_reason: str | None


class StateRecord(TypedDict):
    """JSON shape for the local CLI state file."""

    accounts: list[AccountRecord]
    auth_profiles: list[AuthProfileRecord]


def _empty_state() -> StateRecord:
    return {"accounts": [], "auth_profiles": []}


class LocalStateAccountRepository:
    """Account repository backed by an in-memory view of the state file."""

    def __init__(self, accounts: list[Account]) -> None:
        self._accounts = {account.id: account for account in accounts}

    def get(self, account_id: str) -> Account | None:
        """Return an account by ID."""
        return self._accounts.get(account_id)

    def add(self, account: Account) -> None:
        """Store or replace an account."""
        self._accounts[account.id] = account

    def all(self) -> list[Account]:
        """Return all accounts for serialization."""
        return list(self._accounts.values())


class LocalStateAccountAuthProfileRepository:
    """Account auth profile repository backed by the state file."""

    def __init__(self, profiles: list[AccountAuthProfile]) -> None:
        self._profiles = {
            (profile.account_id, profile.platform): profile for profile in profiles
        }

    def get(self, account_id: str, platform: str) -> AccountAuthProfile | None:
        """Return a profile by account and platform."""
        return self._profiles.get((account_id, platform))

    def add(self, profile: AccountAuthProfile) -> None:
        """Store or replace a profile."""
        self._profiles[(profile.account_id, profile.platform)] = profile

    def all(self) -> list[AccountAuthProfile]:
        """Return all profiles for serialization."""
        return list(self._profiles.values())


class LocalStateUnitOfWork:
    """Unit of work that persists account login metadata to JSON."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        state = self._load_state(state_path)
        self._accounts = LocalStateAccountRepository(
            [
                Account(
                    id=record["id"],
                    platform=record["platform"],
                    enabled=record["enabled"],
                )
                for record in state["accounts"]
            ]
        )
        self._auth_profiles = LocalStateAccountAuthProfileRepository(
            [
                AccountAuthProfile(
                    account_id=record["account_id"],
                    platform=record["platform"],
                    profile_dir=Path(record["profile_dir"]),
                    login_url=record["login_url"],
                    last_login_at=datetime.fromisoformat(record["last_login_at"]),
                    status=record["status"],
                    failure_reason=record["failure_reason"],
                )
                for record in state["auth_profiles"]
            ]
        )
        self._sessions = InMemoryLiveRoomSessionRepository()
        self._comments = InMemoryCommentDispatchRepository()

    @property
    def accounts(self) -> LocalStateAccountRepository:
        """Return account repository."""
        return self._accounts

    @property
    def auth_profiles(self) -> LocalStateAccountAuthProfileRepository:
        """Return account auth profile repository."""
        return self._auth_profiles

    @property
    def sessions(self) -> InMemoryLiveRoomSessionRepository:
        """Return session repository."""
        return self._sessions

    @property
    def comments(self) -> InMemoryCommentDispatchRepository:
        """Return comment dispatch repository."""
        return self._comments

    def commit(self) -> None:
        """Write current account and profile state to disk."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(self._serialize(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _serialize(self) -> StateRecord:
        return {
            "accounts": [
                cast(AccountRecord, asdict(account)) for account in self._accounts.all()
            ],
            "auth_profiles": [
                {
                    "account_id": profile.account_id,
                    "platform": profile.platform,
                    "profile_dir": str(profile.profile_dir),
                    "login_url": profile.login_url,
                    "last_login_at": profile.last_login_at.isoformat(),
                    "status": profile.status,
                    "failure_reason": profile.failure_reason,
                }
                for profile in self._auth_profiles.all()
            ],
        }

    @staticmethod
    def _load_state(state_path: Path) -> StateRecord:
        if not state_path.exists():
            return _empty_state()

        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _empty_state()

        accounts = raw.get("accounts", [])
        profiles = raw.get("auth_profiles", [])
        if not isinstance(accounts, list) or not isinstance(profiles, list):
            return _empty_state()

        return {
            "accounts": cast(list[AccountRecord], accounts),
            "auth_profiles": cast(list[AuthProfileRecord], profiles),
        }
