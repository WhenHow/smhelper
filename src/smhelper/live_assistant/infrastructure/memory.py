"""In-memory repositories for tests and local command wiring."""

from __future__ import annotations

from collections.abc import Iterable

from smhelper.live_assistant.domain.models import (
    Account,
    AccountAuthProfile,
    CommentDispatch,
    LiveRoomSession,
)


class InMemoryAccountRepository:
    """In-memory account repository."""

    def __init__(self, accounts: Iterable[Account] = ()) -> None:
        self._accounts = {account.id: account for account in accounts}

    def get(self, account_id: str) -> Account | None:
        """Return an account by ID."""
        return self._accounts.get(account_id)

    def add(self, account: Account) -> None:
        """Store or replace an account."""
        self._accounts[account.id] = account


class InMemoryAccountAuthProfileRepository:
    """In-memory account auth profile repository."""

    def __init__(self, profiles: Iterable[AccountAuthProfile] = ()) -> None:
        self._profiles = {
            (profile.account_id, profile.platform): profile for profile in profiles
        }

    def get(self, account_id: str, platform: str) -> AccountAuthProfile | None:
        """Return a profile by account and platform."""
        return self._profiles.get((account_id, platform))

    def add(self, profile: AccountAuthProfile) -> None:
        """Store or replace a profile."""
        self._profiles[(profile.account_id, profile.platform)] = profile


class InMemoryLiveRoomSessionRepository:
    """In-memory live room session repository."""

    def __init__(self, sessions: Iterable[LiveRoomSession] = ()) -> None:
        self._sessions = {session.id: session for session in sessions}

    def get(self, session_id: str) -> LiveRoomSession | None:
        """Return a session by ID."""
        return self._sessions.get(session_id)

    def add(self, session: LiveRoomSession) -> None:
        """Store or replace a session."""
        self._sessions[session.id] = session


class InMemoryCommentDispatchRepository:
    """In-memory comment dispatch repository."""

    def __init__(self, comments: Iterable[CommentDispatch] = ()) -> None:
        self._comments = {comment.id: comment for comment in comments}

    def get(self, dispatch_id: str) -> CommentDispatch | None:
        """Return a dispatch record by ID."""
        return self._comments.get(dispatch_id)

    def add(self, dispatch: CommentDispatch) -> None:
        """Store or replace a dispatch record."""
        self._comments[dispatch.id] = dispatch


class InMemoryUnitOfWork:
    """In-memory unit of work for one process."""

    def __init__(
        self,
        accounts: Iterable[Account] = (),
        auth_profiles: Iterable[AccountAuthProfile] = (),
        sessions: Iterable[LiveRoomSession] = (),
        comments: Iterable[CommentDispatch] = (),
    ) -> None:
        self._accounts = InMemoryAccountRepository(accounts)
        self._auth_profiles = InMemoryAccountAuthProfileRepository(auth_profiles)
        self._sessions = InMemoryLiveRoomSessionRepository(sessions)
        self._comments = InMemoryCommentDispatchRepository(comments)
        self.committed = False

    @property
    def accounts(self) -> InMemoryAccountRepository:
        """Return account repository."""
        return self._accounts

    @property
    def auth_profiles(self) -> InMemoryAccountAuthProfileRepository:
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
        """Mark the unit of work as committed."""
        self.committed = True
