from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.live_assistant.application.commands import (
    EnterLiveRoomCommand,
    LoginXhsAccountCommand,
    SendCommentCommand,
)
from smhelper.live_assistant.application.handlers import (
    EnterLiveRoomHandler,
    LoginXhsAccountHandler,
    SendCommentHandler,
)
from smhelper.live_assistant.application.ports import (
    BrowserWindowSize,
    EnterRoomAutomationResult,
    LoginBrowserResult,
    SendCommentAutomationResult,
    VerificationCodeProvider,
)
from smhelper.live_assistant.domain.exceptions import (
    AccountNotAvailable,
    SessionNotReady,
)
from smhelper.live_assistant.domain.models import (
    Account,
    CommentDispatchStatus,
    LiveRoom,
    LiveRoomSession,
    SessionStatus,
)
from smhelper.live_assistant.infrastructure.memory import InMemoryUnitOfWork


@dataclass
class FakeLiveRoomAutomation:
    enter_result: EnterRoomAutomationResult
    send_result: SendCommentAutomationResult
    entered_rooms: list[tuple[str, str]] = field(default_factory=list)
    sent_comments: list[tuple[str, str]] = field(default_factory=list)

    def enter_room(
        self,
        account: Account,
        room: LiveRoom,
    ) -> EnterRoomAutomationResult:
        self.entered_rooms.append((account.id, room.url))
        return self.enter_result

    def send_comment(
        self,
        session: LiveRoomSession,
        text: str,
    ) -> SendCommentAutomationResult:
        self.sent_comments.append((session.id, text))
        return self.send_result


@dataclass
class FakeAccountLoginBrowser:
    result: LoginBrowserResult
    logins: list[
        tuple[
            str,
            str,
            Path,
            str,
            str | None,
            VerificationCodeProvider | None,
            bool,
            BrowserWindowSize,
            bool,
        ]
    ] = field(default_factory=list)

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
        self.logins.append(
            (
                account_id,
                platform,
                profile_dir,
                login_url,
                phone_number,
                verification_code_provider,
                no_proxy,
                window_size,
                observe_code_button,
            )
        )
        return self.result


class FakeVerificationCodeProvider:
    def request_code(self, account_id: str, phone_number: str) -> str:
        return "123456"


def test_login_xhs_account_saves_profile_metadata_after_browser_closes(
    tmp_path: Path,
) -> None:
    logged_in_at = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    uow = InMemoryUnitOfWork()
    browser = FakeAccountLoginBrowser(LoginBrowserResult(success=True))

    result = LoginXhsAccountHandler(
        uow=uow,
        browser=browser,
        clock=FixedClock(logged_in_at),
        profiles_root=tmp_path / "profiles",
    ).handle(LoginXhsAccountCommand(account_id="account-1"))

    profile = uow.auth_profiles.get(account_id="account-1", platform="xhs")
    account = uow.accounts.get("account-1")
    expected_profile_dir = tmp_path / "profiles" / "xhs" / "account-1"
    assert result.account_id == "account-1"
    assert result.profile_dir == expected_profile_dir
    assert result.status == "saved"
    assert account == Account(id="account-1", platform="xhs")
    assert profile is not None
    assert profile.profile_dir == expected_profile_dir
    assert profile.last_login_at == logged_in_at
    assert browser.logins == [
        (
            "account-1",
            "xhs",
            expected_profile_dir,
            "https://www.xiaohongshu.com/explore",
            None,
            None,
            False,
            BrowserWindowSize(width=1280, height=900),
            False,
        )
    ]
    assert uow.committed is True


def test_login_xhs_account_passes_phone_login_options_to_browser(
    tmp_path: Path,
) -> None:
    uow = InMemoryUnitOfWork()
    browser = FakeAccountLoginBrowser(LoginBrowserResult(success=True))
    code_provider = FakeVerificationCodeProvider()

    LoginXhsAccountHandler(
        uow=uow,
        browser=browser,
        clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
        profiles_root=tmp_path / "profiles",
        verification_code_provider=code_provider,
    ).handle(
        LoginXhsAccountCommand(
            account_id="account-1",
            phone_number="13800138000",
            no_proxy=True,
            window_size=BrowserWindowSize(width=1366, height=768),
            observe_code_button=True,
        )
    )

    assert browser.logins[0][4:] == (
        "13800138000",
        code_provider,
        True,
        BrowserWindowSize(width=1366, height=768),
        True,
    )


def test_enter_room_creates_waiting_session_after_automation_succeeds() -> None:
    entered_at = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)
    uow = InMemoryUnitOfWork(accounts=[Account(id="account-1", platform="xhs")])
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )

    result = EnterLiveRoomHandler(
        uow=uow,
        automation=automation,
        clock=FixedClock(entered_at),
        ids=SequenceIdGenerator(["session-1"]),
    ).handle(
        EnterLiveRoomCommand(
            account_id="account-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        )
    )

    session = uow.sessions.get("session-1")
    assert result.session_id == "session-1"
    assert result.status is SessionStatus.WAITING
    assert session is not None
    assert session.status is SessionStatus.WAITING
    assert session.entered_at == entered_at
    assert automation.entered_rooms == [("account-1", "https://example.com/live/1")]
    assert uow.committed is True


def test_enter_room_records_failed_session_after_automation_fails() -> None:
    uow = InMemoryUnitOfWork(accounts=[Account(id="account-1", platform="xhs")])
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(
            success=False,
            failure_reason="login expired",
        ),
        send_result=SendCommentAutomationResult(success=True),
    )

    result = EnterLiveRoomHandler(
        uow=uow,
        automation=automation,
        clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
        ids=SequenceIdGenerator(["session-1"]),
    ).handle(
        EnterLiveRoomCommand(
            account_id="account-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        )
    )

    session = uow.sessions.get("session-1")
    assert result.status is SessionStatus.ENTER_FAILED
    assert result.failure_reason == "login expired"
    assert session is not None
    assert session.status is SessionStatus.ENTER_FAILED
    assert session.failure_reason == "login expired"
    assert uow.committed is True


def test_enter_room_rejects_disabled_account_before_automation() -> None:
    uow = InMemoryUnitOfWork(
        accounts=[Account(id="account-1", platform="xhs", enabled=False)]
    )
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )

    with pytest.raises(AccountNotAvailable, match="disabled"):
        EnterLiveRoomHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            ids=SequenceIdGenerator(["session-1"]),
        ).handle(
            EnterLiveRoomCommand(
                account_id="account-1",
                room_url="https://example.com/live/1",
                platform="xhs",
            )
        )

    assert automation.entered_rooms == []


def test_send_comment_records_success_dispatch_for_waiting_session() -> None:
    sent_at = datetime(2026, 5, 27, 12, 1, tzinfo=UTC)
    session = LiveRoomSession.waiting(
        id="session-1",
        account_id="account-1",
        room_url="https://example.com/live/1",
        platform="xhs",
        entered_at=datetime(2026, 5, 27, 12, 0, tzinfo=UTC),
    )
    uow = InMemoryUnitOfWork(
        accounts=[Account(id="account-1", platform="xhs")],
        sessions=[session],
    )
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )

    result = SendCommentHandler(
        uow=uow,
        automation=automation,
        clock=FixedClock(sent_at),
        ids=SequenceIdGenerator(["dispatch-1"]),
    ).handle(SendCommentCommand(session_id="session-1", text="这个适合油皮吗？"))

    dispatch = uow.comments.get("dispatch-1")
    assert result.dispatch_id == "dispatch-1"
    assert result.status is CommentDispatchStatus.SENT
    assert dispatch is not None
    assert dispatch.session_id == "session-1"
    assert dispatch.text == "这个适合油皮吗？"
    assert dispatch.status is CommentDispatchStatus.SENT
    assert dispatch.sent_at == sent_at
    assert automation.sent_comments == [("session-1", "这个适合油皮吗？")]
    assert uow.committed is True


def test_send_comment_rejects_session_that_is_not_waiting() -> None:
    session = LiveRoomSession.enter_failed(
        id="session-1",
        account_id="account-1",
        room_url="https://example.com/live/1",
        platform="xhs",
        entered_at=datetime(2026, 5, 27, 12, 0, tzinfo=UTC),
        failure_reason="login expired",
    )
    uow = InMemoryUnitOfWork(sessions=[session])
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )

    with pytest.raises(SessionNotReady, match="waiting"):
        SendCommentHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 1, tzinfo=UTC)),
            ids=SequenceIdGenerator(["dispatch-1"]),
        ).handle(SendCommentCommand(session_id="session-1", text="会不会闷痘？"))

    assert automation.sent_comments == []
    assert uow.comments.get("dispatch-1") is None
