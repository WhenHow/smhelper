"""Click commands for the live assistant context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click

from smhelper.core.clock import SystemClock
from smhelper.core.config import RuntimeSettings
from smhelper.core.ids import UuidGenerator
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
from smhelper.live_assistant.application.ports import BrowserWindowSize
from smhelper.live_assistant.application.ports import LiveRoomConsoleBrowserPort
from smhelper.live_assistant.infrastructure.cloakbrowser import (
    CloakBrowserAccountLoginBrowser,
    CloakBrowserLiveRoomAutomation,
    CloakBrowserLiveRoomConsole,
)
from smhelper.live_assistant.infrastructure.local_state import LocalStateUnitOfWork


@dataclass(frozen=True, slots=True)
class LiveAssistantCliRuntime:
    """Handlers used by the live assistant CLI."""

    login_xhs: LoginXhsAccountHandler
    enter_room: EnterLiveRoomHandler
    send_comment: SendCommentHandler
    room_console: LiveRoomConsoleBrowserPort | None = None
    profiles_root: Path = Path(".smhelper/browser-profiles")
    default_platform: str = "xhs"


class ClickVerificationCodeProvider:
    """Read verification codes from the CLI operator."""

    def request_code(self, account_id: str, phone_number: str) -> str:
        """Prompt the operator after the browser has requested a code."""
        return click.prompt(
            f"Verification code for {phone_number} ({account_id})",
            type=str,
        )


class ClickCommentInputProvider:
    """Read live-room comments from the CLI operator."""

    def read_comment(self) -> str | None:
        """Return the next comment, or None when the operator exits."""
        value = click.prompt(
            "Comment (/quit to close)",
            default="",
            show_default=False,
            type=str,
        )
        if value.strip().lower() == "/quit":
            return None
        return value


def create_default_runtime() -> LiveAssistantCliRuntime:
    """Create the default local runtime for CLI commands."""
    settings = RuntimeSettings.from_env()
    uow = LocalStateUnitOfWork(settings.state_path)
    automation = CloakBrowserLiveRoomAutomation()
    login_browser = CloakBrowserAccountLoginBrowser()
    room_console = CloakBrowserLiveRoomConsole()
    return LiveAssistantCliRuntime(
        login_xhs=LoginXhsAccountHandler(
            uow=uow,
            browser=login_browser,
            clock=SystemClock(),
            profiles_root=settings.browser_profiles_dir,
            verification_code_provider=ClickVerificationCodeProvider(),
            platform=settings.default_platform,
        ),
        enter_room=EnterLiveRoomHandler(
            uow=uow,
            automation=automation,
            clock=SystemClock(),
            ids=UuidGenerator(),
        ),
        send_comment=SendCommentHandler(
            uow=uow,
            automation=automation,
            clock=SystemClock(),
            ids=UuidGenerator(),
        ),
        room_console=room_console,
        profiles_root=settings.browser_profiles_dir,
        default_platform=settings.default_platform,
    )


def create_live_assistant_cli(
    runtime: LiveAssistantCliRuntime | None = None,
) -> click.Group:
    """Create the live assistant CLI group."""
    active_runtime = runtime or create_default_runtime()

    @click.group()
    def cli() -> None:
        """Manage live assistant operations."""

    @cli.command("login-xhs")
    @click.option("--account", "account_id", required=True)
    @click.option(
        "--login-url",
        default="https://www.xiaohongshu.com/explore",
        show_default=True,
    )
    @click.option("--phone", "phone_number")
    @click.option("--no-proxy", is_flag=True, default=False)
    @click.option("--window-size", default="1280x900", show_default=True)
    @click.option(
        "--observe-code-button",
        is_flag=True,
        default=False,
        help="Move to the verification-code button and wait without clicking it.",
    )
    def login_xhs(
        account_id: str,
        login_url: str,
        phone_number: str | None,
        no_proxy: bool,
        window_size: str,
        observe_code_button: bool,
    ) -> None:
        """Open CloakBrowser so the operator can log in to XHS."""
        if observe_code_button and phone_number is None:
            raise click.BadParameter("--observe-code-button requires --phone")
        parsed_window_size = parse_window_size(window_size)
        click.echo("Opening CloakBrowser. Log in to XHS, then close the browser.")
        if observe_code_button:
            click.echo(
                "Observation mode: the browser will stop over the code button. "
                "Close the browser when done."
            )
        result = active_runtime.login_xhs.handle(
            LoginXhsAccountCommand(
                account_id=account_id,
                phone_number=phone_number,
                login_url=login_url,
                no_proxy=no_proxy,
                window_size=parsed_window_size,
                observe_code_button=observe_code_button,
            )
        )
        if result.failure_reason is not None:
            raise click.ClickException(result.failure_reason)
        click.echo(
            "account="
            f"{result.account_id} platform={result.platform} "
            f"status={result.status} profile_dir={result.profile_dir}"
        )

    @cli.command("enter-room")
    @click.option("--account", "account_id", required=True)
    @click.option("--room-url", required=True)
    @click.option("--platform", default="xhs", show_default=True)
    def enter_room(account_id: str, room_url: str, platform: str) -> None:
        """Dispatch an account into a live room."""
        result = active_runtime.enter_room.handle(
            EnterLiveRoomCommand(
                account_id=account_id,
                room_url=room_url,
                platform=platform,
            )
        )
        click.echo(f"session={result.session_id} status={result.status.value}")

    @cli.command("send-comment")
    @click.option("--session", "session_id", required=True)
    @click.option("--text", required=True)
    def send_comment(session_id: str, text: str) -> None:
        """Send a comment from a waiting live room session."""
        result = active_runtime.send_comment.handle(
            SendCommentCommand(session_id=session_id, text=text)
        )
        click.echo(f"dispatch={result.dispatch_id} status={result.status.value}")

    @cli.command("room-console")
    @click.option("--account", "account_id", required=True)
    @click.option("--room-url", required=True)
    @click.option("--platform", default="xhs", show_default=True)
    @click.option("--no-proxy", is_flag=True, default=False)
    @click.option("--window-size", default="1280x900", show_default=True)
    def room_console(
        account_id: str,
        room_url: str,
        platform: str,
        no_proxy: bool,
        window_size: str,
    ) -> None:
        """Open an interactive XHS live-room console."""
        if active_runtime.room_console is None:
            raise click.ClickException("room console automation is not configured")

        parsed_window_size = parse_window_size(window_size)
        profile_dir = active_runtime.profiles_root / platform / account_id
        click.echo("Opening live room. Type /quit to close the browser.")
        result = active_runtime.room_console.run(
            profile_dir=profile_dir,
            room_url=room_url,
            comment_provider=ClickCommentInputProvider(),
            no_proxy=no_proxy,
            window_size=parsed_window_size,
        )
        if result.failure_reason is not None:
            raise click.ClickException(result.failure_reason)

        click.echo(
            f"room_status={result.status} comments_sent={result.comments_sent} "
            f"muted_initially={result.muted_initially} unmuted={result.unmuted} "
            f"stream_url={result.stream_url or ''}"
        )

    return cli


def parse_window_size(value: str) -> BrowserWindowSize:
    """Parse WIDTHxHEIGHT CLI input."""
    try:
        width_text, height_text = value.lower().split("x", maxsplit=1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise click.BadParameter("expected WIDTHxHEIGHT, for example 1280x900") from exc
    if width <= 0 or height <= 0:
        raise click.BadParameter("window dimensions must be positive")
    return BrowserWindowSize(width=width, height=height)
