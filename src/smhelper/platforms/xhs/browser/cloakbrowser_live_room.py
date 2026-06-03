"""CloakBrowser-backed Xiaohongshu live-room sessions."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from smhelper.platforms.xhs.browser.selectors import (
    COMMENT_INPUT_SELECTOR,
    COMMENT_SEND_BUTTON_SELECTOR,
    LIVE_FINISH_STATUS_SELECTOR,
    LIVE_PLAYER_SELECTOR,
    LIVE_VIDEO_SELECTOR,
    MUTED_ICON_SELECTOR,
    MUTED_PLAYER_SELECTOR,
    VOLUME_BUTTON_SELECTOR,
)

LIVE_FINISH_TEXT = "\u76f4\u64ad\u5df2\u7ed3\u675f"
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 900
DEFAULT_ACTION_SETTLE_MS = 150
DEFAULT_HEALTH_CHECK_TIMEOUT_MS = 3_000
DEFAULT_LIVE_STATUS_CHECKS = 30
DEFAULT_LIVE_STATUS_WAIT_MS = 1_000
DEFAULT_HUMAN_PRESET = "default"
DEFAULT_HUMAN_CONFIG: dict[str, object] = {
    "idle_between_actions": True,
    "idle_between_duration": (0.1, 0.3),
    "typing_delay": 30,
    "mistype_chance": 0.0,
}


class BrowserLocator(Protocol):
    """Minimal locator API used by XHS live-room automation."""

    @property
    def first(self) -> "BrowserLocator":
        """Return the first matched locator."""

    def count(self) -> int:
        """Return matched element count."""

    def fill(self, value: str) -> object:
        """Fill the matched input."""

    def click(self, timeout: float | None = None) -> object:
        """Click the matched element."""

    def inner_text(self, timeout: float | None = None) -> str:
        """Return element inner text."""

    def is_visible(self, timeout: float | None = None) -> bool:
        """Return whether the matched element is visible."""


class BrowserPage(Protocol):
    """Minimal page API used by XHS live-room automation."""

    def goto(self, url: str) -> object:
        """Navigate to a URL."""

    def locator(self, selector: str) -> BrowserLocator:
        """Return a locator for a selector."""

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> object:
        """Wait for a selector to appear."""

    def wait_for_timeout(self, timeout: float) -> object:
        """Wait for the provided milliseconds."""


class BrowserContext(Protocol):
    """Minimal browser context API for a single worker live-room session."""

    @property
    def pages(self) -> list[BrowserPage]:
        """Return open pages."""

    def new_page(self) -> BrowserPage:
        """Open a new page."""

    def close(self) -> None:
        """Close the browser context."""


class ContextLauncher(Protocol):
    """Callable that launches a CloakBrowser BrowserContext."""

    def __call__(
        self,
        *,
        headless: bool,
        viewport: dict[str, int] | None,
        humanize: bool,
        human_preset: str,
        human_config: dict[str, object],
        args: list[str],
        storage_state: str,
    ) -> BrowserContext:
        """Launch and return a browser context."""


@dataclass(slots=True)
class XhsCloakBrowserLiveRoomSession:
    """One open XHS live-room page backed by a CloakBrowser context."""

    context: BrowserContext
    page: BrowserPage
    action_settle_ms: int = DEFAULT_ACTION_SETTLE_MS

    def send_comment(self, text: str) -> None:
        """Send one approved comment from this live room page."""
        normalized = text.strip()
        if not normalized:
            raise RuntimeError("comment text must not be blank")

        self.page.wait_for_selector(COMMENT_INPUT_SELECTOR, timeout=10_000)
        self.page.locator(COMMENT_INPUT_SELECTOR).first.fill(normalized)
        self.page.wait_for_selector(COMMENT_SEND_BUTTON_SELECTOR, timeout=10_000)
        self.page.locator(COMMENT_SEND_BUTTON_SELECTOR).first.click(timeout=10_000)
        self.page.wait_for_timeout(self.action_settle_ms)

    def check_health(self) -> None:
        """Verify the session page is still ready for comment operations."""
        self.page.wait_for_selector(
            COMMENT_INPUT_SELECTOR,
            timeout=DEFAULT_HEALTH_CHECK_TIMEOUT_MS,
        )
        if not _is_visible(page=self.page, selector=COMMENT_INPUT_SELECTOR):
            raise RuntimeError("comment input is not available")

    def close(self) -> None:
        """Close the underlying browser context."""
        self.context.close()


@dataclass(slots=True)
class XhsCloakBrowserLiveRoomSessionManager:
    """Open live-room sessions using CloakBrowser and a storage-state file."""

    launcher: ContextLauncher | None = None
    headless: bool = False
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT
    no_proxy: bool = False
    live_status_checks: int = DEFAULT_LIVE_STATUS_CHECKS
    live_status_wait_ms: int = DEFAULT_LIVE_STATUS_WAIT_MS
    action_settle_ms: int = DEFAULT_ACTION_SETTLE_MS
    human_preset: str = DEFAULT_HUMAN_PRESET
    human_config: dict[str, object] = field(
        default_factory=lambda: dict(DEFAULT_HUMAN_CONFIG)
    )

    def open_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> XhsCloakBrowserLiveRoomSession:
        """Open the XHS live room and return a session ready for comments."""
        context: BrowserContext | None = None
        try:
            context = self._launcher(
                headless=self.headless,
                viewport={"width": self.window_width, "height": self.window_height},
                humanize=True,
                human_preset=self.human_preset,
                human_config=self.human_config,
                args=self._launch_args(),
                storage_state=str(storage_state_path),
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(room_url)
            _wait_for_live_room(page, self.live_status_checks, self.live_status_wait_ms)
            _unmute_if_needed(page, self.action_settle_ms)
            return XhsCloakBrowserLiveRoomSession(
                context=context,
                page=page,
                action_settle_ms=self.action_settle_ms,
            )
        except Exception:
            if context is not None:
                with suppress(Exception):
                    context.close()
            raise

    @property
    def _launcher(self) -> ContextLauncher:
        return self.launcher or _load_default_context_launcher()

    def _launch_args(self) -> list[str]:
        args = [f"--window-size={self.window_width},{self.window_height}"]
        if self.no_proxy:
            args.append("--no-proxy-server")
        return args


def _load_default_context_launcher() -> ContextLauncher:
    cloakbrowser = import_module("cloakbrowser")
    launcher = getattr(cloakbrowser, "launch_context")
    return cast(ContextLauncher, launcher)


def _wait_for_live_room(
    page: BrowserPage,
    checks: int,
    wait_ms: int,
) -> None:
    for _ in range(checks):
        finish_text = _inner_text(page, LIVE_FINISH_STATUS_SELECTOR)
        if LIVE_FINISH_TEXT in finish_text:
            raise RuntimeError("live room is not live")
        if _is_visible(page, LIVE_PLAYER_SELECTOR) and _is_visible(
            page, LIVE_VIDEO_SELECTOR
        ):
            return
        page.wait_for_timeout(wait_ms)
    raise RuntimeError("live room status timed out")


def _unmute_if_needed(page: BrowserPage, action_settle_ms: int) -> None:
    if not (
        _is_visible(page, MUTED_PLAYER_SELECTOR)
        or _is_visible(page, MUTED_ICON_SELECTOR)
    ):
        return

    page.wait_for_selector(VOLUME_BUTTON_SELECTOR, timeout=10_000)
    page.locator(VOLUME_BUTTON_SELECTOR).first.click(timeout=10_000)
    page.wait_for_timeout(action_settle_ms)


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


def _count(page: BrowserPage, selector: str) -> int:
    return page.locator(selector).count()
