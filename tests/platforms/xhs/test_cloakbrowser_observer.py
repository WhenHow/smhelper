from __future__ import annotations

from collections.abc import Callable

import pytest

from smhelper.live.application.ports.live_stream_observer import (
    LiveStreamObservationStatus,
)
from smhelper.platforms.xhs.browser.cloakbrowser_observer import (
    XhsCloakBrowserLiveStreamObserver,
)
from smhelper.platforms.xhs.browser.selectors import (
    LIVE_FINISH_STATUS_SELECTOR,
    LIVE_PLAYER_SELECTOR,
    LIVE_VIDEO_SELECTOR,
)


class FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class FakePage:
    def __init__(self) -> None:
        self.visited_urls: list[str] = []
        self.locators: dict[str, FakeLocator] = {}
        self.request_urls_on_goto: list[str] = []
        self.evaluate_result: object = []
        self.waited_timeouts: list[float] = []
        self.goto_error: Exception | None = None
        self._request_handlers: list[Callable[[FakeRequest], object]] = []

    def goto(self, url: str) -> None:
        if self.goto_error is not None:
            raise self.goto_error
        self.visited_urls.append(url)
        for request_url in self.request_urls_on_goto:
            request = FakeRequest(request_url)
            for handler in self._request_handlers:
                handler(request)

    def on(self, event: str, handler: Callable[[FakeRequest], object]) -> None:
        if event == "request":
            self._request_handlers.append(handler)

    def locator(self, selector: str) -> "FakeLocator":
        return self.locators.setdefault(selector, FakeLocator(count=0))

    def evaluate(self, expression: str) -> object:
        return self.evaluate_result

    def wait_for_timeout(self, timeout: float) -> None:
        self.waited_timeouts.append(timeout)


class FakeLocator:
    def __init__(
        self,
        *,
        count: int = 1,
        text: str = "",
        visible: bool = True,
    ) -> None:
        self._count = count
        self._text = text
        self._visible = visible

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return self._count

    def inner_text(self, timeout: float | None = None) -> str:
        return self._text

    def is_visible(self, timeout: float | None = None) -> bool:
        return self._visible


class FakeContext:
    def __init__(self, page: FakePage | None = None) -> None:
        self.page = page or FakePage()
        self.pages = [self.page]
        self.closed = False

    def new_page(self) -> FakePage:
        self.page = FakePage()
        self.pages = [self.page]
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeContextLauncher:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.calls: list[
            tuple[
                bool,
                dict[str, int] | None,
                bool,
                str,
                dict[str, object],
                list[str],
            ]
        ] = []

    def __call__(
        self,
        *,
        headless: bool,
        viewport: dict[str, int] | None,
        humanize: bool,
        human_preset: str,
        human_config: dict[str, object],
        args: list[str],
    ) -> FakeContext:
        self.calls.append(
            (
                headless,
                viewport,
                humanize,
                human_preset,
                human_config,
                args,
            )
        )
        return self.context


def test_cloakbrowser_observer_returns_captured_stream_url() -> None:
    page = FakePage()
    page.request_urls_on_goto = [
        "https://example.com/not-stream.jpg",
        "https://stream.example/live.flv",
        "https://stream.example/live.m3u8",
    ]
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()
    context = FakeContext(page)
    launcher = FakeContextLauncher(context)

    observation = XhsCloakBrowserLiveStreamObserver(
        launcher=launcher,
        observation_checks=1,
        no_proxy=True,
    ).observe(room_url="https://www.xiaohongshu.com/livestream/1")

    assert observation.status is LiveStreamObservationStatus.LIVE
    assert observation.stream_url == "https://stream.example/live.m3u8"
    assert page.visited_urls == ["https://www.xiaohongshu.com/livestream/1"]
    assert launcher.calls == [
        (
            True,
            {"width": 1280, "height": 900},
            True,
            "default",
            {
                "idle_between_actions": True,
                "idle_between_duration": (0.1, 0.3),
                "typing_delay": 30,
                "mistype_chance": 0.0,
            },
            ["--window-size=1280,900", "--no-proxy-server"],
        )
    ]
    assert context.closed is True


def test_cloakbrowser_observer_session_keeps_context_open_until_closed() -> None:
    page = FakePage()
    page.request_urls_on_goto = ["https://stream.example/live.flv"]
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()
    context = FakeContext(page)

    session = XhsCloakBrowserLiveStreamObserver(
        launcher=FakeContextLauncher(context),
    ).open_session(room_url="https://www.xiaohongshu.com/livestream/1")

    assert context.closed is False
    assert session.observe().status is LiveStreamObservationStatus.LIVE

    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(
        text="\u76f4\u64ad\u5df2\u7ed3\u675f"
    )
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator(count=0)

    assert session.observe().status is LiveStreamObservationStatus.NOT_LIVE

    session.close()

    assert context.closed is True
    assert page.visited_urls == ["https://www.xiaohongshu.com/livestream/1"]


def test_cloakbrowser_observer_session_closes_context_when_navigation_fails() -> None:
    page = FakePage()
    page.goto_error = RuntimeError("navigation failed")
    context = FakeContext(page)

    with pytest.raises(RuntimeError, match="navigation failed"):
        XhsCloakBrowserLiveStreamObserver(
            launcher=FakeContextLauncher(context),
        ).open_session(room_url="https://www.xiaohongshu.com/livestream/1")

    assert context.closed is True


def test_cloakbrowser_observer_falls_back_to_performance_entries() -> None:
    page = FakePage()
    page.evaluate_result = [
        "https://example.com/image.jpg",
        "https://stream.example/live.flv",
    ]
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()

    observation = XhsCloakBrowserLiveStreamObserver(
        launcher=FakeContextLauncher(FakeContext(page)),
        observation_checks=1,
    ).observe(room_url="https://www.xiaohongshu.com/livestream/1")

    assert observation.status is LiveStreamObservationStatus.LIVE
    assert observation.stream_url == "https://stream.example/live.flv"


def test_cloakbrowser_observer_returns_not_live_for_finished_room() -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(text="直播已结束")

    observation = XhsCloakBrowserLiveStreamObserver(
        launcher=FakeContextLauncher(FakeContext(page)),
        observation_checks=1,
    ).observe(room_url="https://www.xiaohongshu.com/livestream/1")

    assert observation.status is LiveStreamObservationStatus.NOT_LIVE
    assert observation.stream_url is None


def test_cloakbrowser_observer_returns_unknown_after_timeout() -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator(count=0)

    observation = XhsCloakBrowserLiveStreamObserver(
        launcher=FakeContextLauncher(FakeContext(page)),
        observation_checks=2,
        observation_wait_ms=250,
    ).observe(room_url="https://www.xiaohongshu.com/livestream/1")

    assert observation.status is LiveStreamObservationStatus.UNKNOWN
    assert observation.stream_url is None
    assert page.waited_timeouts == [250, 250]
