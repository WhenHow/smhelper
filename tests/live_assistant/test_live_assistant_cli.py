from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.live_assistant.application.commands import EnterLiveRoomCommand
from smhelper.live_assistant.application.handlers import (
    EnterLiveRoomHandler,
    LoginXhsAccountHandler,
    SendCommentHandler,
)
from smhelper.live_assistant.application.ports import (
    BrowserWindowSize,
    CommentInputProvider,
    EnterRoomAutomationResult,
    LoginBrowserResult,
    LiveRoomConsoleResult,
    SendCommentAutomationResult,
    VerificationCodeProvider,
)
from smhelper.live_assistant.domain.models import Account, LiveRoom, LiveRoomSession
from smhelper.live_assistant.infrastructure.memory import InMemoryUnitOfWork
from smhelper.live_assistant.interfaces.cli import (
    LiveAssistantCliRuntime,
    create_live_assistant_cli,
)


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
                phone_number,
                verification_code_provider,
                no_proxy,
                window_size,
                observe_code_button,
            )
        )
        return self.result


@dataclass
class FakeRoomConsole:
    result_status: str = "stopped"
    calls: list[tuple[Path, str, bool, BrowserWindowSize, list[str]]] = field(
        default_factory=list
    )

    def run(
        self,
        *,
        profile_dir: Path,
        room_url: str,
        comment_provider: CommentInputProvider,
        no_proxy: bool,
        window_size: BrowserWindowSize,
    ) -> LiveRoomConsoleResult:
        comments: list[str] = []
        while True:
            comment = comment_provider.read_comment()
            if comment is None:
                break
            if comment.strip():
                comments.append(comment)
        self.calls.append((profile_dir, room_url, no_proxy, window_size, comments))
        return LiveRoomConsoleResult(
            status=self.result_status,
            comments_sent=len(comments),
            muted_initially=True,
            unmuted=True,
            stream_url="https://example.com/live.flv",
        )


class StaticVerificationCodeProvider:
    def __init__(self, code: str) -> None:
        self.code = code
        self.requests: list[tuple[str, str]] = []

    def request_code(self, account_id: str, phone_number: str) -> str:
        self.requests.append((account_id, phone_number))
        return self.code


def test_enter_room_command_outputs_waiting_session() -> None:
    uow = InMemoryUnitOfWork(accounts=[Account(id="account-1", platform="xhs")])
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )
    runtime = LiveAssistantCliRuntime(
        login_xhs=LoginXhsAccountHandler(
            uow=uow,
            browser=FakeAccountLoginBrowser(LoginBrowserResult(success=True)),
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            profiles_root=Path("profiles"),
        ),
        enter_room=EnterLiveRoomHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            ids=SequenceIdGenerator(["session-1"]),
        ),
        send_comment=SendCommentHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 1, tzinfo=UTC)),
            ids=SequenceIdGenerator(["dispatch-1"]),
        ),
    )

    result = CliRunner().invoke(
        create_live_assistant_cli(runtime),
        [
            "enter-room",
            "--account",
            "account-1",
            "--room-url",
            "https://example.com/live/1",
            "--platform",
            "xhs",
        ],
    )

    assert result.exit_code == 0
    assert "session-1" in result.output
    assert "waiting" in result.output


def test_send_comment_command_outputs_dispatch_result() -> None:
    uow = InMemoryUnitOfWork(accounts=[Account(id="account-1", platform="xhs")])
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )
    enter_handler = EnterLiveRoomHandler(
        uow=uow,
        automation=automation,
        clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
        ids=SequenceIdGenerator(["session-1"]),
    )
    enter_handler.handle(
        EnterLiveRoomCommand(
            account_id="account-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        )
    )
    runtime = LiveAssistantCliRuntime(
        login_xhs=LoginXhsAccountHandler(
            uow=uow,
            browser=FakeAccountLoginBrowser(LoginBrowserResult(success=True)),
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            profiles_root=Path("profiles"),
        ),
        enter_room=enter_handler,
        send_comment=SendCommentHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 1, tzinfo=UTC)),
            ids=SequenceIdGenerator(["dispatch-1"]),
        ),
    )

    result = CliRunner().invoke(
        create_live_assistant_cli(runtime),
        [
            "send-comment",
            "--session",
            "session-1",
            "--text",
            "Is it suitable for sensitive skin?",
        ],
    )

    assert result.exit_code == 0
    assert "dispatch-1" in result.output
    assert "sent" in result.output


def test_login_xhs_command_outputs_saved_profile(tmp_path: Path) -> None:
    uow = InMemoryUnitOfWork()
    browser = FakeAccountLoginBrowser(LoginBrowserResult(success=True))
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )
    runtime = LiveAssistantCliRuntime(
        login_xhs=LoginXhsAccountHandler(
            uow=uow,
            browser=browser,
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            profiles_root=tmp_path / "profiles",
        ),
        enter_room=EnterLiveRoomHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            ids=SequenceIdGenerator(["session-1"]),
        ),
        send_comment=SendCommentHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 1, tzinfo=UTC)),
            ids=SequenceIdGenerator(["dispatch-1"]),
        ),
    )

    result = CliRunner().invoke(
        create_live_assistant_cli(runtime),
        ["login-xhs", "--account", "account-1"],
    )

    assert result.exit_code == 0
    assert "account=account-1" in result.output
    assert "platform=xhs" in result.output
    assert "status=saved" in result.output
    assert browser.logins[0][0] is None


def test_login_xhs_command_passes_phone_options_to_handler(tmp_path: Path) -> None:
    uow = InMemoryUnitOfWork()
    browser = FakeAccountLoginBrowser(LoginBrowserResult(success=True))
    code_provider = StaticVerificationCodeProvider("654321")
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )
    runtime = LiveAssistantCliRuntime(
        login_xhs=LoginXhsAccountHandler(
            uow=uow,
            browser=browser,
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            profiles_root=tmp_path / "profiles",
            verification_code_provider=code_provider,
        ),
        enter_room=EnterLiveRoomHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            ids=SequenceIdGenerator(["session-1"]),
        ),
        send_comment=SendCommentHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 1, tzinfo=UTC)),
            ids=SequenceIdGenerator(["dispatch-1"]),
        ),
    )

    result = CliRunner().invoke(
        create_live_assistant_cli(runtime),
        [
            "login-xhs",
            "--account",
            "account-1",
            "--phone",
            "13800138000",
            "--window-size",
            "1366x768",
            "--no-proxy",
            "--observe-code-button",
        ],
    )

    assert result.exit_code == 0
    assert browser.logins[0] == (
        "13800138000",
        code_provider,
        True,
        BrowserWindowSize(width=1366, height=768),
        True,
    )


def test_room_console_command_waits_for_comments_until_quit(tmp_path: Path) -> None:
    uow = InMemoryUnitOfWork()
    automation = FakeLiveRoomAutomation(
        enter_result=EnterRoomAutomationResult(success=True),
        send_result=SendCommentAutomationResult(success=True),
    )
    room_console = FakeRoomConsole()
    runtime = LiveAssistantCliRuntime(
        login_xhs=LoginXhsAccountHandler(
            uow=uow,
            browser=FakeAccountLoginBrowser(LoginBrowserResult(success=True)),
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            profiles_root=tmp_path / "profiles",
        ),
        enter_room=EnterLiveRoomHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 0, tzinfo=UTC)),
            ids=SequenceIdGenerator(["session-1"]),
        ),
        send_comment=SendCommentHandler(
            uow=uow,
            automation=automation,
            clock=FixedClock(datetime(2026, 5, 27, 12, 1, tzinfo=UTC)),
            ids=SequenceIdGenerator(["dispatch-1"]),
        ),
        room_console=room_console,
        profiles_root=tmp_path / "profiles",
    )

    result = CliRunner().invoke(
        create_live_assistant_cli(runtime),
        [
            "room-console",
            "--account",
            "account-0",
            "--room-url",
            "https://www.xiaohongshu.com/livestream/1",
            "--no-proxy",
            "--window-size",
            "1366x768",
        ],
        input="hello live\n/quit\n",
    )

    assert result.exit_code == 0
    assert room_console.calls == [
        (
            tmp_path / "profiles" / "xhs" / "account-0",
            "https://www.xiaohongshu.com/livestream/1",
            True,
            BrowserWindowSize(width=1366, height=768),
            ["hello live"],
        )
    ]
    assert "room_status=stopped" in result.output
    assert "comments_sent=1" in result.output
    assert "unmuted=True" in result.output
