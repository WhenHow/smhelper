"""Command DTOs accepted by live assistant application handlers."""

from __future__ import annotations

from dataclasses import dataclass

from smhelper.live_assistant.application.ports import BrowserWindowSize

XHS_LOGIN_URL = "https://www.xiaohongshu.com/explore"


@dataclass(frozen=True, slots=True)
class LoginXhsAccountCommand:
    """Request to open a persistent browser profile for XHS login."""

    account_id: str
    phone_number: str | None = None
    login_url: str = XHS_LOGIN_URL
    no_proxy: bool = False
    window_size: BrowserWindowSize = BrowserWindowSize()
    observe_code_button: bool = False


@dataclass(frozen=True, slots=True)
class EnterLiveRoomCommand:
    """Request to dispatch an account into a live room."""

    account_id: str
    room_url: str
    platform: str = "xhs"


@dataclass(frozen=True, slots=True)
class SendCommentCommand:
    """Request to send a comment from a waiting live room session."""

    session_id: str
    text: str
