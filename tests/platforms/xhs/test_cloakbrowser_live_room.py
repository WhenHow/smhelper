from __future__ import annotations

from pathlib import Path

from smhelper.platforms.xhs.browser.cloakbrowser_live_room import (
    XhsCloakBrowserLiveRoomSessionManager,
)
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


class FakePage:
    def __init__(self) -> None:
        self.visited_urls: list[str] = []
        self.locators: dict[str, FakeLocator] = {}
        self.waited_selectors: list[tuple[str, float | None]] = []
        self.waited_timeouts: list[float] = []
        self.events: list[tuple[str, str, str | None]] = []

    def goto(self, url: str) -> None:
        self.visited_urls.append(url)

    def locator(self, selector: str) -> "FakeLocator":
        locator = self.locators.setdefault(selector, FakeLocator(count=0))
        locator.bind(selector=selector, events=self.events)
        return locator

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> None:
        self.waited_selectors.append((selector, timeout))

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
        self._selector: str | None = None
        self._events: list[tuple[str, str, str | None]] | None = None
        self.fills: list[str] = []
        self.clicks = 0

    def bind(
        self,
        *,
        selector: str,
        events: list[tuple[str, str, str | None]],
    ) -> None:
        self._selector = selector
        self._events = events

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return self._count

    def fill(self, value: str) -> None:
        self.fills.append(value)
        if self._selector is not None and self._events is not None:
            self._events.append(("fill", self._selector, value))

    def click(self, timeout: float | None = None) -> None:
        self.clicks += 1
        if self._selector is not None and self._events is not None:
            self._events.append(("click", self._selector, None))

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
                str,
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
        storage_state: str,
    ) -> FakeContext:
        self.calls.append(
            (
                headless,
                viewport,
                humanize,
                human_preset,
                human_config,
                args,
                storage_state,
            )
        )
        return self.context


def test_cloakbrowser_session_manager_opens_room_with_storage_state_and_unmutes(
    tmp_path: Path,
) -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()
    page.locators[MUTED_PLAYER_SELECTOR] = FakeLocator()
    page.locators[VOLUME_BUTTON_SELECTOR] = FakeLocator()
    context = FakeContext(page)
    launcher = FakeContextLauncher(context)
    manager = XhsCloakBrowserLiveRoomSessionManager(
        launcher=launcher,
        live_status_checks=1,
        no_proxy=True,
    )
    storage_state_path = tmp_path / "storage_state.json"

    live_session = manager.open_live_room(
        session_id="session-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        storage_state_path=storage_state_path,
    )

    assert live_session.page is page
    assert launcher.calls == [
        (
            False,
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
            str(storage_state_path),
        )
    ]
    assert page.visited_urls == ["https://www.xiaohongshu.com/livestream/1"]
    assert page.locator(VOLUME_BUTTON_SELECTOR).clicks == 1
    assert page.waited_timeouts == [150]


def test_cloakbrowser_live_session_sends_comment_and_closes_context(
    tmp_path: Path,
) -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()
    page.locators[MUTED_PLAYER_SELECTOR] = FakeLocator(count=0)
    page.locators[MUTED_ICON_SELECTOR] = FakeLocator(count=0)
    page.locators[COMMENT_INPUT_SELECTOR] = FakeLocator()
    page.locators[COMMENT_SEND_BUTTON_SELECTOR] = FakeLocator()
    context = FakeContext(page)
    manager = XhsCloakBrowserLiveRoomSessionManager(
        launcher=FakeContextLauncher(context),
        live_status_checks=1,
    )

    live_session = manager.open_live_room(
        session_id="session-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        storage_state_path=tmp_path / "storage_state.json",
    )
    live_session.send_comment("  Is this suitable for oily skin?  ")
    live_session.close()

    assert page.locator(COMMENT_INPUT_SELECTOR).fills == [
        "Is this suitable for oily skin?"
    ]
    assert page.locator(COMMENT_SEND_BUTTON_SELECTOR).clicks == 1
    assert page.waited_selectors == [
        (COMMENT_INPUT_SELECTOR, 10_000),
        (COMMENT_SEND_BUTTON_SELECTOR, 10_000),
    ]
    assert page.waited_timeouts == [150]
    assert context.closed is True
    assert _event_index(page, "fill", COMMENT_INPUT_SELECTOR) < _event_index(
        page, "click", COMMENT_SEND_BUTTON_SELECTOR
    )


def test_cloakbrowser_live_session_checks_comment_input_health(
    tmp_path: Path,
) -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()
    page.locators[MUTED_PLAYER_SELECTOR] = FakeLocator(count=0)
    page.locators[MUTED_ICON_SELECTOR] = FakeLocator(count=0)
    page.locators[COMMENT_INPUT_SELECTOR] = FakeLocator()
    context = FakeContext(page)
    manager = XhsCloakBrowserLiveRoomSessionManager(
        launcher=FakeContextLauncher(context),
        live_status_checks=1,
    )
    live_session = manager.open_live_room(
        session_id="session-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        storage_state_path=tmp_path / "storage_state.json",
    )

    live_session.check_health()

    assert page.waited_selectors == [(COMMENT_INPUT_SELECTOR, 3_000)]


def test_cloakbrowser_live_session_health_fails_when_comment_input_is_missing(
    tmp_path: Path,
) -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()
    page.locators[MUTED_PLAYER_SELECTOR] = FakeLocator(count=0)
    page.locators[MUTED_ICON_SELECTOR] = FakeLocator(count=0)
    page.locators[COMMENT_INPUT_SELECTOR] = FakeLocator(count=0)
    context = FakeContext(page)
    manager = XhsCloakBrowserLiveRoomSessionManager(
        launcher=FakeContextLauncher(context),
        live_status_checks=1,
    )
    live_session = manager.open_live_room(
        session_id="session-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        storage_state_path=tmp_path / "storage_state.json",
    )

    try:
        live_session.check_health()
    except RuntimeError as exc:
        assert str(exc) == "comment input is not available"
    else:
        raise AssertionError("expected health check to fail without comment input")


def test_cloakbrowser_session_manager_closes_context_when_live_has_finished(
    tmp_path: Path,
) -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(
        text="\u76f4\u64ad\u5df2\u7ed3\u675f"
    )
    context = FakeContext(page)
    manager = XhsCloakBrowserLiveRoomSessionManager(
        launcher=FakeContextLauncher(context),
        live_status_checks=1,
    )

    try:
        manager.open_live_room(
            session_id="session-1",
            room_url="https://www.xiaohongshu.com/livestream/1",
            storage_state_path=tmp_path / "storage_state.json",
        )
    except RuntimeError as exc:
        assert str(exc) == "live room is not live"
    else:
        raise AssertionError("expected open_live_room to reject finished live room")

    assert context.closed is True


def test_cloakbrowser_live_session_rejects_blank_comment(tmp_path: Path) -> None:
    page = FakePage()
    page.locators[LIVE_FINISH_STATUS_SELECTOR] = FakeLocator(count=0)
    page.locators[LIVE_PLAYER_SELECTOR] = FakeLocator()
    page.locators[LIVE_VIDEO_SELECTOR] = FakeLocator()
    page.locators[MUTED_PLAYER_SELECTOR] = FakeLocator(count=0)
    page.locators[MUTED_ICON_SELECTOR] = FakeLocator(count=0)
    context = FakeContext(page)
    manager = XhsCloakBrowserLiveRoomSessionManager(
        launcher=FakeContextLauncher(context),
        live_status_checks=1,
    )
    live_session = manager.open_live_room(
        session_id="session-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        storage_state_path=tmp_path / "storage_state.json",
    )

    try:
        live_session.send_comment("   ")
    except RuntimeError as exc:
        assert str(exc) == "comment text must not be blank"
    else:
        raise AssertionError("expected blank comment to fail")


def _event_index(page: FakePage, action: str, selector: str) -> int:
    for index, (event_action, event_selector, _) in enumerate(page.events):
        if event_action == action and event_selector == selector:
            return index
    raise AssertionError(f"event not found: {action} {selector}")
