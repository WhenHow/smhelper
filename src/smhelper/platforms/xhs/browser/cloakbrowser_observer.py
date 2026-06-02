"""CloakBrowser-backed anonymous Xiaohongshu live-stream observer."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from importlib import import_module
from typing import Protocol, cast

from smhelper.live.application.ports.live_stream_observer import (
    LiveStreamObservation,
    LiveStreamObservationStatus,
)
from smhelper.platforms.xhs.browser.cloakbrowser_live_room import (
    DEFAULT_HUMAN_CONFIG,
    DEFAULT_HUMAN_PRESET,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
)
from smhelper.platforms.xhs.browser.selectors import (
    LIVE_FINISH_STATUS_SELECTOR,
    LIVE_PLAYER_SELECTOR,
    LIVE_VIDEO_SELECTOR,
)
from smhelper.platforms.xhs.browser.stream_discovery import (
    XhsLiveRoomSignals,
    observe_xhs_live_stream,
    select_latest_stream_url,
)

STREAM_URL_EXPRESSION = r"""
() => performance.getEntriesByType("resource")
  .map((entry) => entry.name)
  .filter((name) => /\.flv|\.m3u8|live-source-play/i.test(name))
"""


class BrowserRequest(Protocol):
    """Minimal request API used for stream URL capture."""

    @property
    def url(self) -> str:
        """Return the request URL."""


class BrowserLocator(Protocol):
    """Minimal locator API used by the anonymous live-stream observer."""

    @property
    def first(self) -> "BrowserLocator":
        """Return the first matched locator."""

    def count(self) -> int:
        """Return matched element count."""

    def inner_text(self, timeout: float | None = None) -> str:
        """Return element inner text."""

    def is_visible(self, timeout: float | None = None) -> bool:
        """Return whether the matched element is visible."""


class BrowserPage(Protocol):
    """Minimal page API used by the anonymous live-stream observer."""

    def goto(self, url: str) -> object:
        """Navigate to a URL."""

    def on(self, event: str, handler: Callable[[BrowserRequest], object]) -> object:
        """Register a page event handler."""

    def locator(self, selector: str) -> BrowserLocator:
        """Return a locator for a selector."""

    def evaluate(self, expression: str) -> object:
        """Evaluate JavaScript in the page."""

    def wait_for_timeout(self, timeout: float) -> object:
        """Wait for the provided milliseconds."""


class BrowserContext(Protocol):
    """Minimal browser context API used by the observer."""

    @property
    def pages(self) -> list[BrowserPage]:
        """Return open pages."""

    def new_page(self) -> BrowserPage:
        """Open a new page."""

    def close(self) -> None:
        """Close the browser context."""


class ContextLauncher(Protocol):
    """Callable that launches an anonymous CloakBrowser BrowserContext."""

    def __call__(
        self,
        *,
        headless: bool,
        viewport: dict[str, int] | None,
        humanize: bool,
        human_preset: str,
        human_config: dict[str, object],
        args: list[str],
    ) -> BrowserContext:
        """Launch and return a browser context."""


@dataclass(slots=True)
class XhsCloakBrowserLiveStreamObserver:
    """Observe an XHS live room anonymously and return stream status."""

    launcher: ContextLauncher | None = None
    headless: bool = True
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT
    no_proxy: bool = False
    observation_checks: int = 30
    observation_wait_ms: int = 1_000
    human_preset: str = DEFAULT_HUMAN_PRESET
    human_config: dict[str, object] = field(
        default_factory=lambda: dict(DEFAULT_HUMAN_CONFIG)
    )

    def observe(self, *, room_url: str) -> LiveStreamObservation:
        """Open the live room once and observe status plus stream URL."""
        context: BrowserContext | None = None
        captured_stream_urls: list[str] = []
        live_without_stream: LiveStreamObservation | None = None
        try:
            context = self._launcher(
                headless=self.headless,
                viewport={"width": self.window_width, "height": self.window_height},
                humanize=True,
                human_preset=self.human_preset,
                human_config=self.human_config,
                args=self._launch_args(),
            )
            page = context.pages[0] if context.pages else context.new_page()
            _attach_stream_capture(page, captured_stream_urls)
            page.goto(room_url)

            for _ in range(self.observation_checks):
                observation = _observe_page(page, captured_stream_urls)
                if observation.status is LiveStreamObservationStatus.NOT_LIVE:
                    return observation
                if observation.status is LiveStreamObservationStatus.LIVE:
                    if observation.stream_url is not None:
                        return observation
                    live_without_stream = observation
                page.wait_for_timeout(self.observation_wait_ms)

            return live_without_stream or LiveStreamObservation(
                status=LiveStreamObservationStatus.UNKNOWN
            )
        finally:
            if context is not None:
                with suppress(Exception):
                    context.close()

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


def _attach_stream_capture(page: BrowserPage, stream_urls: list[str]) -> None:
    def capture(request: BrowserRequest) -> None:
        stream_url = select_latest_stream_url([request.url])
        if stream_url is not None:
            stream_urls.append(stream_url)

    with suppress(Exception):
        page.on("request", capture)


def _observe_page(
    page: BrowserPage,
    captured_stream_urls: list[str],
) -> LiveStreamObservation:
    stream_url = _extract_stream_url(page, captured_stream_urls)
    return observe_xhs_live_stream(
        XhsLiveRoomSignals(
            finish_text=_inner_text(page, LIVE_FINISH_STATUS_SELECTOR),
            player_visible=_is_visible(page, LIVE_PLAYER_SELECTOR),
            video_visible=_is_visible(page, LIVE_VIDEO_SELECTOR),
            stream_url=stream_url,
        )
    )


def _extract_stream_url(
    page: BrowserPage,
    captured_stream_urls: list[str],
) -> str | None:
    captured_stream_url = select_latest_stream_url(captured_stream_urls)
    if captured_stream_url is not None:
        return captured_stream_url

    with suppress(Exception):
        urls = page.evaluate(STREAM_URL_EXPRESSION)
        if isinstance(urls, list):
            return select_latest_stream_url(
                [url for url in urls if isinstance(url, str)]
            )

    return None


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
