"""Application ports implemented by infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from smhelper.live_assistant.domain.models import (
    Account,
    LiveRoom,
    LiveRoomSession,
)
from smhelper.live_assistant.domain.repositories import (
    AccountAuthProfileRepository,
    AccountRepository,
    CommentDispatchRepository,
    LiveRoomSessionRepository,
)


@dataclass(frozen=True, slots=True)
class EnterRoomAutomationResult:
    """Result returned by live-room automation after an enter-room attempt."""

    success: bool
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SendCommentAutomationResult:
    """Result returned by live-room automation after a comment attempt."""

    success: bool
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LoginBrowserResult:
    """Result returned after an interactive account login browser closes."""

    success: bool
    failure_reason: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class LiveRoomConsoleResult:
    """Result returned after an interactive live-room console exits."""

    status: str
    comments_sent: int = 0
    muted_initially: bool = False
    unmuted: bool = False
    stream_url: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserWindowSize:
    """Browser window and viewport size for interactive automation."""

    width: int = 1280
    height: int = 900


class VerificationCodeProvider(Protocol):
    """Provides operator-entered verification codes."""

    def request_code(self, account_id: str, phone_number: str) -> str:
        """Return the verification code entered by the operator."""


class CommentInputProvider(Protocol):
    """Provides operator-entered live-room comments."""

    def read_comment(self) -> str | None:
        """Return the next comment, or None when the console should exit."""


class AccountLoginBrowserPort(Protocol):
    """Browser boundary for manual account login."""

    def login(
        self,
        *,
        account_id: str,
        platform: str,
        profile_dir: Path,
        login_url: str,
        phone_number: str | None,
        verification_code_provider: VerificationCodeProvider | None,
        no_proxy: bool,
        window_size: BrowserWindowSize,
        observe_code_button: bool,
    ) -> LoginBrowserResult:
        """Open a browser profile for login and return after it closes."""


class LiveRoomConsoleBrowserPort(Protocol):
    """Browser boundary for an interactive live-room console."""

    def run(
        self,
        *,
        profile_dir: Path,
        room_url: str,
        comment_provider: CommentInputProvider,
        no_proxy: bool,
        window_size: BrowserWindowSize,
    ) -> LiveRoomConsoleResult:
        """Open a live room and process operator comments until exit."""


class LiveRoomAutomationPort(Protocol):
    """Browser automation boundary for live room operations."""

    def enter_room(
        self,
        account: Account,
        room: LiveRoom,
    ) -> EnterRoomAutomationResult:
        """Enter the live room with the provided account."""

    def send_comment(
        self,
        session: LiveRoomSession,
        text: str,
    ) -> SendCommentAutomationResult:
        """Send a comment from an existing live room session."""


class UnitOfWork(Protocol):
    """Coordinates repositories and commits one application use case."""

    @property
    def accounts(self) -> AccountRepository:
        """Return account repository."""

    @property
    def auth_profiles(self) -> AccountAuthProfileRepository:
        """Return account auth profile repository."""

    @property
    def sessions(self) -> LiveRoomSessionRepository:
        """Return live room session repository."""

    @property
    def comments(self) -> CommentDispatchRepository:
        """Return comment dispatch repository."""

    def commit(self) -> None:
        """Persist changes made during the use case."""
