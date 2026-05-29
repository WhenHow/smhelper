"""CloakBrowser automation adapters."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

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

PHONE_INPUT_SELECTOR = 'input[name="xhs-pc-web-phone"]'
VERIFICATION_INPUT_SELECTOR = 'input[placeholder="\u8f93\u5165\u9a8c\u8bc1\u7801"]'
LOGIN_BUTTON_SELECTOR = "#login-btn"
LOGGED_IN_NAV_SELECTOR = "li.user.side-bar-component"
LOGGED_IN_NAV_TEXT = "\u6211"
LOGIN_MODAL_SELECTOR = ".login-modal"
CODE_BUTTON_SELECTOR = ".code-button.active"
AGREEMENT_SELECTOR = ".agreements .agree-icon"
SUBMIT_BUTTON_SELECTOR = "button.submit"
ERROR_MESSAGE_SELECTOR = ".login-modal .err-msg"
LOGIN_BUTTON_STILL_VISIBLE_REASON = "login button is still visible"
LIVE_FINISH_STATUS_SELECTOR = ".live-finish .live-status"
LIVE_FINISH_TEXT = "\u76f4\u64ad\u5df2\u7ed3\u675f"
LIVE_PLAYER_SELECTOR = ".player-ref-container.xgplayer-is-live"
LIVE_VIDEO_SELECTOR = ".main-player video"
MUTED_PLAYER_SELECTOR = ".player-ref-container.xgplayer-volume-muted"
MUTED_ICON_SELECTOR = ".xgplayer-icon-muted"
VOLUME_BUTTON_SELECTOR = ".xgplayer-volume"
COMMENT_INPUT_SELECTOR = "#input-area"
COMMENT_SEND_BUTTON_SELECTOR = "button.send"
LIVE_STATUS = "live"
NOT_LIVE_STATUS = "not_live"
STOPPED_STATUS = "stopped"
FAILED_STATUS = "failed"
LIVE_ROOM_STATUS_TIMEOUT_REASON = "live room status timed out"
STREAM_URL_EXPRESSION = r"""
() => performance.getEntriesByType("resource")
  .map((entry) => entry.name)
  .filter((name) => /\.flv|\.m3u8|live-source-play/i.test(name))
"""
CHECKED_CLASS_MARKERS = frozenset({"active", "checked", "selected", "is-checked"})
CHECKED_ATTRIBUTE_VALUES = frozenset({"true", "1", "checked", "selected", "active"})
OBSERVED_STATUS = "observed"
HUMAN_PRESET = "careful"
HUMAN_CONFIG: dict[str, object] = {
    "idle_between_actions": True,
    "idle_between_duration": (0.4, 1.0),
    "typing_delay": 100,
    "mistype_chance": 0.02,
}
ROOM_CONSOLE_HUMAN_PRESET = "default"
ROOM_CONSOLE_HUMAN_CONFIG: dict[str, object] = {
    "idle_between_actions": True,
    "idle_between_duration": (0.1, 0.3),
    "typing_delay": 30,
    "mistype_chance": 0.0,
}
ROOM_CONSOLE_ACTION_SETTLE_MS = 150


class BrowserLocator(Protocol):
    """Minimal locator API used by the login adapter."""

    @property
    def first(self) -> "BrowserLocator":
        """Return the first matched locator."""

    def count(self) -> int:
        """Return matched element count."""

    def fill(self, value: str) -> object:
        """Fill the matched input."""

    def click(self, timeout: float | None = None) -> object:
        """Click the matched element."""

    def hover(self, timeout: float | None = None) -> object:
        """Hover over the matched element."""

    def inner_text(self, timeout: float | None = None) -> str:
        """Return element inner text."""

    def is_visible(self, timeout: float | None = None) -> bool:
        """Return whether the matched element is visible."""

    def is_checked(self, timeout: float | None = None) -> bool:
        """Return whether the locator is checked when it supports check state."""

    def get_attribute(self, name: str, timeout: float | None = None) -> str | None:
        """Return an attribute value from the matched element."""


class BrowserPage(Protocol):
    """Minimal page API used by this adapter."""

    def goto(self, url: str) -> object:
        """Navigate to a URL."""

    def on(self, event: str, handler: Callable[["BrowserRequest"], object]) -> object:
        """Register a page event handler."""

    def locator(self, selector: str) -> BrowserLocator:
        """Return a locator for the selector."""

    def evaluate(self, expression: str, arg: object | None = None) -> object:
        """Evaluate JavaScript in the page."""

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> object:
        """Wait for a selector to appear."""

    def wait_for_timeout(self, timeout: float) -> object:
        """Wait for the provided milliseconds."""


class BrowserContext(Protocol):
    """Minimal persistent browser context API used by this adapter."""

    @property
    def pages(self) -> list[BrowserPage]:
        """Return open pages."""

    def new_page(self) -> BrowserPage:
        """Open a new page."""

    def wait_for_event(self, event: str, timeout: float | None = None) -> object:
        """Wait for a browser context event."""

    def close(self) -> None:
        """Close the context."""


class BrowserRequest(Protocol):
    """Minimal request API used for stream URL capture."""

    @property
    def url(self) -> str:
        """Return the request URL."""


class PersistentContextLauncher(Protocol):
    """Callable that opens a CloakBrowser persistent context."""

    def __call__(
        self,
        user_data_dir: str | Path,
        *,
        headless: bool,
        viewport: dict[str, int] | None,
        humanize: bool,
        human_preset: str,
        human_config: dict[str, object],
        args: list[str],
    ) -> BrowserContext:
        """Launch a persistent browser context."""


class CloakBrowserAccountLoginBrowser:
    """Open a persistent CloakBrowser profile for manual account login."""

    def __init__(self, launcher: PersistentContextLauncher | None = None) -> None:
        self._launcher = launcher or _load_default_launcher()

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
        """Open the login page and return after the browser context closes."""
        profile_dir.mkdir(parents=True, exist_ok=True)
        context: BrowserContext | None = None
        try:
            launch_args = [f"--window-size={window_size.width},{window_size.height}"]
            if no_proxy:
                launch_args.append("--no-proxy-server")
            context = self._launcher(
                profile_dir,
                headless=False,
                viewport={"width": window_size.width, "height": window_size.height},
                humanize=True,
                human_preset=HUMAN_PRESET,
                human_config=HUMAN_CONFIG,
                args=launch_args,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(login_url)
            if phone_number is None:
                context.wait_for_event("close", timeout=0)
            else:
                return _login_with_phone(
                    context=context,
                    page=page,
                    account_id=account_id,
                    phone_number=phone_number,
                    verification_code_provider=verification_code_provider,
                    observe_code_button=observe_code_button,
                )
        except Exception as exc:
            return LoginBrowserResult(success=False, failure_reason=str(exc))
        finally:
            if context is not None:
                with suppress(Exception):
                    context.close()

        return LoginBrowserResult(success=True)


class CloakBrowserLiveRoomConsole:
    """Interactive CloakBrowser console for an XHS live room."""

    def __init__(self, launcher: PersistentContextLauncher | None = None) -> None:
        self._launcher = launcher or _load_default_launcher()

    def run(
        self,
        *,
        profile_dir: Path,
        room_url: str,
        comment_provider: CommentInputProvider,
        no_proxy: bool,
        window_size: BrowserWindowSize,
    ) -> LiveRoomConsoleResult:
        """Open a live room, unmute it, and send operator comments until exit."""
        profile_dir.mkdir(parents=True, exist_ok=True)
        context: BrowserContext | None = None
        captured_stream_urls: list[str] = []
        comments_sent = 0
        muted_initially = False
        unmuted = False
        stream_url: str | None = None
        try:
            launch_args = [f"--window-size={window_size.width},{window_size.height}"]
            if no_proxy:
                launch_args.append("--no-proxy-server")
            context = self._launcher(
                profile_dir,
                headless=False,
                viewport={"width": window_size.width, "height": window_size.height},
                humanize=True,
                human_preset=ROOM_CONSOLE_HUMAN_PRESET,
                human_config=ROOM_CONSOLE_HUMAN_CONFIG,
                args=launch_args,
            )
            page = context.pages[0] if context.pages else context.new_page()
            _attach_stream_capture(page, captured_stream_urls)
            page.goto(room_url)

            status = _wait_for_live_room_status(page, captured_stream_urls)
            stream_url = _extract_stream_url(page, captured_stream_urls)
            if status != LIVE_STATUS:
                return LiveRoomConsoleResult(
                    status=status,
                    comments_sent=0,
                    stream_url=stream_url,
                    failure_reason=(
                        LIVE_ROOM_STATUS_TIMEOUT_REASON
                        if status == FAILED_STATUS
                        else None
                    ),
                )

            muted_initially = _is_live_room_muted(page)
            if muted_initially:
                page.locator(VOLUME_BUTTON_SELECTOR).first.click(timeout=10_000)
                page.wait_for_timeout(ROOM_CONSOLE_ACTION_SETTLE_MS)
                unmuted = True

            while True:
                comment = comment_provider.read_comment()
                if comment is None:
                    break
                normalized = comment.strip()
                if not normalized:
                    continue
                page.wait_for_selector(COMMENT_INPUT_SELECTOR, timeout=10_000)
                page.locator(COMMENT_INPUT_SELECTOR).first.fill(normalized)
                page.wait_for_selector(COMMENT_SEND_BUTTON_SELECTOR, timeout=10_000)
                page.locator(COMMENT_SEND_BUTTON_SELECTOR).first.click(timeout=10_000)
                comments_sent += 1
                page.wait_for_timeout(ROOM_CONSOLE_ACTION_SETTLE_MS)

            return LiveRoomConsoleResult(
                status=STOPPED_STATUS,
                comments_sent=comments_sent,
                muted_initially=muted_initially,
                unmuted=unmuted,
                stream_url=stream_url,
            )
        except Exception as exc:
            return LiveRoomConsoleResult(
                status=FAILED_STATUS,
                comments_sent=comments_sent,
                muted_initially=muted_initially,
                unmuted=unmuted,
                stream_url=stream_url,
                failure_reason=str(exc),
            )
        finally:
            if context is not None:
                with suppress(Exception):
                    context.close()


def _load_default_launcher() -> PersistentContextLauncher:
    cloakbrowser = import_module("cloakbrowser")
    launcher = getattr(cloakbrowser, "launch_persistent_context")
    return cast(PersistentContextLauncher, launcher)


def _login_with_phone(
    *,
    context: BrowserContext,
    page: BrowserPage,
    account_id: str,
    phone_number: str,
    verification_code_provider: VerificationCodeProvider | None,
    observe_code_button: bool,
) -> LoginBrowserResult:
    """Perform the XHS phone verification-code login flow."""
    if verification_code_provider is None:
        return LoginBrowserResult(
            success=False,
            failure_reason="verification code provider is required for phone login",
        )

    if _count(page, PHONE_INPUT_SELECTOR) == 0:
        if _count(page, LOGIN_BUTTON_SELECTOR) > 0:
            page.locator(LOGIN_BUTTON_SELECTOR).first.click(timeout=10_000)
        page.wait_for_selector(PHONE_INPUT_SELECTOR, timeout=10_000)

    page.locator(PHONE_INPUT_SELECTOR).first.fill(phone_number)
    page.wait_for_timeout(500)
    _ensure_agreement_checked(page)
    if observe_code_button:
        page.locator(CODE_BUTTON_SELECTOR).first.hover(timeout=10_000)
        context.wait_for_event("close", timeout=0)
        return LoginBrowserResult(success=True, status=OBSERVED_STATUS)

    page.locator(CODE_BUTTON_SELECTOR).first.click(timeout=10_000)
    verification_code = verification_code_provider.request_code(
        account_id,
        phone_number,
    ).strip()
    if not verification_code:
        return LoginBrowserResult(
            success=False,
            failure_reason="verification code must not be blank",
        )

    page.wait_for_selector(VERIFICATION_INPUT_SELECTOR, timeout=10_000)
    page.locator(VERIFICATION_INPUT_SELECTOR).first.fill(verification_code)
    page.locator(SUBMIT_BUTTON_SELECTOR).first.click(timeout=10_000)
    return _wait_for_login_result(page)


def _ensure_agreement_checked(page: BrowserPage) -> None:
    if _count(page, AGREEMENT_SELECTOR) == 0:
        return

    agreement = page.locator(AGREEMENT_SELECTOR).first
    if _agreement_is_checked(agreement):
        return

    agreement.click(timeout=5_000)


def _agreement_is_checked(locator: BrowserLocator) -> bool:
    with suppress(Exception):
        if locator.is_checked(timeout=500):
            return True

    for attribute_name in ("aria-checked", "data-checked", "data-state"):
        with suppress(Exception):
            attribute_value = locator.get_attribute(attribute_name, timeout=500)
            if attribute_value is not None:
                return attribute_value.strip().lower() in CHECKED_ATTRIBUTE_VALUES

    with suppress(Exception):
        class_value = locator.get_attribute("class", timeout=500) or ""
        class_names = {class_name.strip().lower() for class_name in class_value.split()}
        return bool(class_names & CHECKED_CLASS_MARKERS)

    return False


def _wait_for_login_result(page: BrowserPage) -> LoginBrowserResult:
    for _ in range(30):
        if _is_logged_in(page):
            return LoginBrowserResult(success=True)

        error_text = _inner_text(page, ERROR_MESSAGE_SELECTOR)
        if error_text:
            return LoginBrowserResult(success=False, failure_reason=error_text)

        if _count(page, LOGIN_MODAL_SELECTOR) == 0 and _is_visible(
            page,
            LOGIN_BUTTON_SELECTOR,
        ):
            return LoginBrowserResult(
                success=False,
                failure_reason=LOGIN_BUTTON_STILL_VISIBLE_REASON,
            )

        page.wait_for_timeout(1_000)

    return LoginBrowserResult(
        success=False,
        failure_reason="login result timed out",
    )


def _count(page: BrowserPage, selector: str) -> int:
    return page.locator(selector).count()


def _inner_text(page: BrowserPage, selector: str) -> str:
    if _count(page, selector) == 0:
        return ""
    return page.locator(selector).first.inner_text(timeout=500).strip()


def _is_visible(page: BrowserPage, selector: str) -> bool:
    if _count(page, selector) == 0:
        return False
    with suppress(Exception):
        return page.locator(selector).first.is_visible(timeout=500)
    return False


def _is_logged_in(page: BrowserPage) -> bool:
    if not _is_visible(page, LOGGED_IN_NAV_SELECTOR):
        return False

    nav_text = _inner_text(page, LOGGED_IN_NAV_SELECTOR)
    return any(line.strip() == LOGGED_IN_NAV_TEXT for line in nav_text.splitlines())


def _attach_stream_capture(page: BrowserPage, stream_urls: list[str]) -> None:
    def capture(request: BrowserRequest) -> None:
        if _is_stream_url(request.url):
            stream_urls.append(request.url)

    with suppress(Exception):
        page.on("request", capture)


def _wait_for_live_room_status(
    page: BrowserPage,
    captured_stream_urls: list[str],
) -> str:
    for _ in range(30):
        finish_text = _inner_text(page, LIVE_FINISH_STATUS_SELECTOR)
        if LIVE_FINISH_TEXT in finish_text:
            return NOT_LIVE_STATUS
        if _is_visible(page, LIVE_PLAYER_SELECTOR) and _is_visible(
            page,
            LIVE_VIDEO_SELECTOR,
        ):
            return LIVE_STATUS
        if _extract_stream_url(page, captured_stream_urls) is not None:
            return LIVE_STATUS
        page.wait_for_timeout(1_000)
    return FAILED_STATUS


def _is_live_room_muted(page: BrowserPage) -> bool:
    return _is_visible(page, MUTED_PLAYER_SELECTOR) or _is_visible(
        page,
        MUTED_ICON_SELECTOR,
    )


def _extract_stream_url(
    page: BrowserPage,
    captured_stream_urls: list[str],
) -> str | None:
    for url in reversed(captured_stream_urls):
        if _is_stream_url(url):
            return url

    with suppress(Exception):
        urls = page.evaluate(STREAM_URL_EXPRESSION)
        if isinstance(urls, list):
            for url in reversed(urls):
                if isinstance(url, str) and _is_stream_url(url):
                    return url

    return None


def _is_stream_url(url: str) -> bool:
    lowered = url.lower()
    return ".flv" in lowered or ".m3u8" in lowered or "live-source-play" in lowered


class CloakBrowserLiveRoomAutomation:
    """Placeholder adapter boundary for future real CloakBrowser automation."""

    def enter_room(
        self,
        account: Account,
        room: LiveRoom,
    ) -> EnterRoomAutomationResult:
        """Report that real browser automation has not been wired yet."""
        return EnterRoomAutomationResult(
            success=False,
            failure_reason=(
                "CloakBrowser automation is not configured for "
                f"account {account.id!r} and room {room.url!r}"
            ),
        )

    def send_comment(
        self,
        session: LiveRoomSession,
        text: str,
    ) -> SendCommentAutomationResult:
        """Report that real browser automation has not been wired yet."""
        return SendCommentAutomationResult(
            success=False,
            failure_reason=(
                f"CloakBrowser automation is not configured for session {session.id!r}"
            ),
        )
