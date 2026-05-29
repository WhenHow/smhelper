from __future__ import annotations

from pathlib import Path

from smhelper.live_assistant.application.ports import BrowserWindowSize
from smhelper.live_assistant.infrastructure.cloakbrowser import (
    CloakBrowserAccountLoginBrowser,
    CloakBrowserLiveRoomConsole,
)

VERIFICATION_INPUT_SELECTOR = 'input[placeholder="\u8f93\u5165\u9a8c\u8bc1\u7801"]'


class FakePage:
    def __init__(self) -> None:
        self.visited_urls: list[str] = []
        self.locators: dict[str, FakeLocator] = {}
        self.waited_selectors: list[tuple[str, float | None]] = []
        self.waited_timeouts: list[float] = []
        self.events: list[tuple[str, str, str | None]] = []
        self.evaluations: list[tuple[str, object | None]] = []
        self.evaluate_result: object = None

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

    def evaluate(self, expression: str, arg: object | None = None) -> object:
        self.evaluations.append((expression, arg))
        self.events.append(("evaluate", "", None))
        return self.evaluate_result


class FakeLocator:
    def __init__(
        self,
        count: int = 1,
        text: str = "",
        visible: bool = True,
        checked: bool = False,
        attributes: dict[str, str] | None = None,
    ) -> None:
        self._count = count
        self._text = text
        self._visible = visible
        self._checked = checked
        self._attributes = attributes or {}
        self._selector: str | None = None
        self._events: list[tuple[str, str, str | None]] | None = None
        self.fills: list[str] = []
        self.clicks = 0
        self.hovers = 0

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

    def hover(self, timeout: float | None = None) -> None:
        self.hovers += 1
        if self._selector is not None and self._events is not None:
            self._events.append(("hover", self._selector, None))

    def inner_text(self, timeout: float | None = None) -> str:
        return self._text

    def is_visible(self, timeout: float | None = None) -> bool:
        return self._visible

    def is_checked(self, timeout: float | None = None) -> bool:
        return self._checked

    def get_attribute(self, name: str, timeout: float | None = None) -> str | None:
        return self._attributes.get(name)


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()
        self.pages = [self.page]
        self.waited_events: list[tuple[str, float | None]] = []
        self.closed = False

    def new_page(self) -> FakePage:
        self.page = FakePage()
        self.pages = [self.page]
        return self.page

    def wait_for_event(self, event: str, timeout: float | None = None) -> None:
        self.waited_events.append((event, timeout))

    def close(self) -> None:
        self.closed = True


class FakeLauncher:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.calls: list[
            tuple[
                Path,
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
        user_data_dir: str | Path,
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
                Path(user_data_dir),
                headless,
                viewport,
                humanize,
                human_preset,
                human_config,
                args,
            )
        )
        return self.context


def test_cloakbrowser_login_launches_persistent_profile_and_waits_for_close(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    launcher = FakeLauncher(context)
    browser = CloakBrowserAccountLoginBrowser(launcher=launcher)

    result = browser.login(
        account_id="account-1",
        platform="xhs",
        profile_dir=tmp_path / "profile",
        login_url="https://www.xiaohongshu.com/explore",
        phone_number=None,
        verification_code_provider=None,
        no_proxy=False,
        window_size=BrowserWindowSize(width=1280, height=900),
        observe_code_button=False,
    )

    assert result.success is True
    assert launcher.calls == [
        (
            tmp_path / "profile",
            False,
            {"width": 1280, "height": 900},
            True,
            "careful",
            {
                "idle_between_actions": True,
                "idle_between_duration": (0.4, 1.0),
                "typing_delay": 100,
                "mistype_chance": 0.02,
            },
            ["--window-size=1280,900"],
        )
    ]
    assert context.page.visited_urls == ["https://www.xiaohongshu.com/explore"]
    assert context.waited_events == [("close", 0)]
    assert context.closed is True
    assert (tmp_path / "profile").is_dir()


class StaticCodeProvider:
    def request_code(self, account_id: str, phone_number: str) -> str:
        return "654321"


def test_cloakbrowser_phone_login_fills_phone_code_and_submits(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    page = context.page
    page.locators['input[name="xhs-pc-web-phone"]'] = FakeLocator()
    page.locators[".code-button.active"] = FakeLocator()
    page.locators[VERIFICATION_INPUT_SELECTOR] = FakeLocator()
    page.locators[".agreements .agree-icon"] = FakeLocator()
    page.locators["button.submit"] = FakeLocator()
    page.locators[".login-modal .err-msg"] = FakeLocator(count=1, text="")
    page.locators[".login-modal"] = FakeLocator(count=0)
    page.locators["li.user.side-bar-component"] = FakeLocator(text="\u6211")
    launcher = FakeLauncher(context)
    browser = CloakBrowserAccountLoginBrowser(launcher=launcher)

    result = browser.login(
        account_id="account-1",
        platform="xhs",
        profile_dir=tmp_path / "profile",
        login_url="https://www.xiaohongshu.com/explore",
        phone_number="13800138000",
        verification_code_provider=StaticCodeProvider(),
        no_proxy=True,
        window_size=BrowserWindowSize(width=1366, height=768),
        observe_code_button=False,
    )

    assert result.success is True
    assert launcher.calls[0] == (
        tmp_path / "profile",
        False,
        {"width": 1366, "height": 768},
        True,
        "careful",
        {
            "idle_between_actions": True,
            "idle_between_duration": (0.4, 1.0),
            "typing_delay": 100,
            "mistype_chance": 0.02,
        },
        ["--window-size=1366,768", "--no-proxy-server"],
    )
    assert page.locator('input[name="xhs-pc-web-phone"]').fills == ["13800138000"]
    assert page.locator(".code-button.active").clicks == 1
    assert page.locator(VERIFICATION_INPUT_SELECTOR).fills == ["654321"]
    assert page.locator(".agreements .agree-icon").clicks == 1
    assert page.locator("button.submit").clicks == 1
    assert _event_index(
        page,
        "fill",
        'input[name="xhs-pc-web-phone"]',
        "13800138000",
    ) < _event_index(page, "click", ".agreements .agree-icon")
    assert _event_index(page, "click", ".agreements .agree-icon") < _event_index(
        page, "click", ".code-button.active"
    )
    assert _event_index(page, "fill", VERIFICATION_INPUT_SELECTOR, "654321") < (
        _event_index(page, "click", "button.submit")
    )


def test_cloakbrowser_phone_login_does_not_toggle_checked_agreement(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    page = context.page
    page.locators['input[name="xhs-pc-web-phone"]'] = FakeLocator()
    page.locators[".code-button.active"] = FakeLocator()
    page.locators[VERIFICATION_INPUT_SELECTOR] = FakeLocator()
    page.locators[".agreements .agree-icon"] = FakeLocator(
        attributes={"class": "agree-icon active"}
    )
    page.locators["button.submit"] = FakeLocator()
    page.locators[".login-modal .err-msg"] = FakeLocator(count=1, text="")
    page.locators[".login-modal"] = FakeLocator(count=0)
    page.locators["li.user.side-bar-component"] = FakeLocator(text="\u6211")
    launcher = FakeLauncher(context)
    browser = CloakBrowserAccountLoginBrowser(launcher=launcher)

    result = browser.login(
        account_id="account-1",
        platform="xhs",
        profile_dir=tmp_path / "profile",
        login_url="https://www.xiaohongshu.com/explore",
        phone_number="13800138000",
        verification_code_provider=StaticCodeProvider(),
        no_proxy=True,
        window_size=BrowserWindowSize(width=1366, height=768),
        observe_code_button=False,
    )

    assert result.success is True
    assert page.locator(".agreements .agree-icon").clicks == 0
    assert page.locator(".code-button.active").clicks == 1


def test_cloakbrowser_phone_login_succeeds_when_me_nav_appears_with_modal_left_open(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    page = context.page
    page.locators['input[name="xhs-pc-web-phone"]'] = FakeLocator()
    page.locators[".code-button.active"] = FakeLocator()
    page.locators[VERIFICATION_INPUT_SELECTOR] = FakeLocator()
    page.locators[".agreements .agree-icon"] = FakeLocator()
    page.locators["button.submit"] = FakeLocator()
    page.locators[".login-modal .err-msg"] = FakeLocator(count=1, text="")
    page.locators[".login-modal"] = FakeLocator(count=1)
    page.locators["li.user.side-bar-component"] = FakeLocator(text="\u6211")
    launcher = FakeLauncher(context)
    browser = CloakBrowserAccountLoginBrowser(launcher=launcher)

    result = browser.login(
        account_id="account-1",
        platform="xhs",
        profile_dir=tmp_path / "profile",
        login_url="https://www.xiaohongshu.com/explore",
        phone_number="13800138000",
        verification_code_provider=StaticCodeProvider(),
        no_proxy=True,
        window_size=BrowserWindowSize(width=1366, height=768),
        observe_code_button=False,
    )

    assert result.success is True
    assert page.locator("button.submit").clicks == 1


def test_cloakbrowser_phone_login_does_not_succeed_when_modal_closes_but_login_button_remains(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    page = context.page
    page.locators['input[name="xhs-pc-web-phone"]'] = FakeLocator()
    page.locators[".code-button.active"] = FakeLocator()
    page.locators[VERIFICATION_INPUT_SELECTOR] = FakeLocator()
    page.locators[".agreements .agree-icon"] = FakeLocator()
    page.locators["button.submit"] = FakeLocator()
    page.locators[".login-modal .err-msg"] = FakeLocator(count=1, text="")
    page.locators[".login-modal"] = FakeLocator(count=0)
    page.locators["#login-btn"] = FakeLocator(text="\u767b\u5f55")
    browser = CloakBrowserAccountLoginBrowser(launcher=FakeLauncher(context))

    result = browser.login(
        account_id="account-1",
        platform="xhs",
        profile_dir=tmp_path / "profile",
        login_url="https://www.xiaohongshu.com/explore",
        phone_number="13800138000",
        verification_code_provider=StaticCodeProvider(),
        no_proxy=True,
        window_size=BrowserWindowSize(width=1366, height=768),
        observe_code_button=False,
    )

    assert result.success is False
    assert result.failure_reason == "login button is still visible"


class RecordingCodeProvider:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def request_code(self, account_id: str, phone_number: str) -> str:
        self.requests.append((account_id, phone_number))
        return "654321"


def test_cloakbrowser_phone_login_can_stop_after_moving_to_code_button(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    page = context.page
    page.locators['input[name="xhs-pc-web-phone"]'] = FakeLocator()
    page.locators[".code-button.active"] = FakeLocator()
    page.locators[VERIFICATION_INPUT_SELECTOR] = FakeLocator()
    page.locators[".agreements .agree-icon"] = FakeLocator()
    page.locators["button.submit"] = FakeLocator()
    page.locators[".login-modal .err-msg"] = FakeLocator(count=1, text="")
    page.locators[".login-modal"] = FakeLocator(count=1)
    code_provider = RecordingCodeProvider()
    browser = CloakBrowserAccountLoginBrowser(launcher=FakeLauncher(context))

    result = browser.login(
        account_id="account-1",
        platform="xhs",
        profile_dir=tmp_path / "profile",
        login_url="https://www.xiaohongshu.com/explore",
        phone_number="13800138000",
        verification_code_provider=code_provider,
        no_proxy=True,
        window_size=BrowserWindowSize(width=1366, height=768),
        observe_code_button=True,
    )

    assert result.success is True
    assert result.status == "observed"
    assert code_provider.requests == []
    assert page.locator(".code-button.active").hovers == 1
    assert page.locator(".code-button.active").clicks == 0
    assert page.locator(VERIFICATION_INPUT_SELECTOR).fills == []
    assert page.locator("button.submit").clicks == 0
    assert context.waited_events == [("close", 0)]


class QueueCommentProvider:
    def __init__(self, values: list[str | None]) -> None:
        self._values = values

    def read_comment(self) -> str | None:
        if not self._values:
            return None
        return self._values.pop(0)


def test_live_room_console_exits_when_live_has_finished(tmp_path: Path) -> None:
    context = FakeContext()
    page = context.page
    page.locators[".live-finish .live-status"] = FakeLocator(
        text="\u76f4\u64ad\u5df2\u7ed3\u675f"
    )
    console = CloakBrowserLiveRoomConsole(launcher=FakeLauncher(context))

    result = console.run(
        profile_dir=tmp_path / "profile",
        room_url="https://www.xiaohongshu.com/livestream/1",
        comment_provider=QueueCommentProvider(["should not be read"]),
        no_proxy=True,
        window_size=BrowserWindowSize(width=1280, height=900),
    )

    assert result.status == "not_live"
    assert result.comments_sent == 0
    assert page.visited_urls == ["https://www.xiaohongshu.com/livestream/1"]
    assert context.closed is True


def test_live_room_console_uses_fast_humanized_controls(tmp_path: Path) -> None:
    context = FakeContext()
    page = context.page
    page.locators[".live-finish .live-status"] = FakeLocator(count=0)
    page.locators[".player-ref-container.xgplayer-is-live"] = FakeLocator()
    page.locators[".main-player video"] = FakeLocator()
    page.locators[".player-ref-container.xgplayer-volume-muted"] = FakeLocator(count=0)
    page.locators[".xgplayer-icon-muted"] = FakeLocator(count=0)
    launcher = FakeLauncher(context)
    console = CloakBrowserLiveRoomConsole(launcher=launcher)

    result = console.run(
        profile_dir=tmp_path / "profile",
        room_url="https://www.xiaohongshu.com/livestream/1",
        comment_provider=QueueCommentProvider([None]),
        no_proxy=False,
        window_size=BrowserWindowSize(width=1280, height=900),
    )

    assert result.status == "stopped"
    assert launcher.calls == [
        (
            tmp_path / "profile",
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
            ["--window-size=1280,900"],
        )
    ]


def test_live_room_console_unmutes_live_room_before_waiting_for_comments(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    page = context.page
    page.locators[".live-finish .live-status"] = FakeLocator(count=0)
    page.locators[".player-ref-container.xgplayer-is-live"] = FakeLocator()
    page.locators[".main-player video"] = FakeLocator()
    page.locators[".player-ref-container.xgplayer-volume-muted"] = FakeLocator()
    page.locators[".xgplayer-volume"] = FakeLocator()
    console = CloakBrowserLiveRoomConsole(launcher=FakeLauncher(context))

    result = console.run(
        profile_dir=tmp_path / "profile",
        room_url="https://www.xiaohongshu.com/livestream/1",
        comment_provider=QueueCommentProvider([None]),
        no_proxy=False,
        window_size=BrowserWindowSize(width=1280, height=900),
    )

    assert result.status == "stopped"
    assert result.muted_initially is True
    assert result.unmuted is True
    assert page.locator(".xgplayer-volume").clicks == 1
    assert page.waited_timeouts == [150]
    assert context.closed is True


def test_live_room_console_sends_comment_and_waits_for_next_input(
    tmp_path: Path,
) -> None:
    context = FakeContext()
    page = context.page
    page.locators[".live-finish .live-status"] = FakeLocator(count=0)
    page.locators[".player-ref-container.xgplayer-is-live"] = FakeLocator()
    page.locators[".main-player video"] = FakeLocator()
    page.locators[".player-ref-container.xgplayer-volume-muted"] = FakeLocator(count=0)
    page.locators[".xgplayer-icon-muted"] = FakeLocator(count=0)
    page.locators["#input-area"] = FakeLocator()
    page.locators["button.send"] = FakeLocator()
    console = CloakBrowserLiveRoomConsole(launcher=FakeLauncher(context))

    result = console.run(
        profile_dir=tmp_path / "profile",
        room_url="https://www.xiaohongshu.com/livestream/1",
        comment_provider=QueueCommentProvider(["hello live", None]),
        no_proxy=False,
        window_size=BrowserWindowSize(width=1280, height=900),
    )

    assert result.status == "stopped"
    assert result.comments_sent == 1
    assert page.locator("#input-area").fills == ["hello live"]
    assert page.locator("button.send").clicks == 1
    assert page.waited_timeouts == [150]
    assert _event_index(page, "fill", "#input-area", "hello live") < _event_index(
        page, "click", "button.send"
    )


def _event_index(
    page: FakePage,
    action: str,
    selector: str,
    value: str | None = None,
) -> int:
    return page.events.index((action, selector, value))


def _event_count(page: FakePage, action: str, selector: str | None = None) -> int:
    return sum(
        1
        for event_action, event_selector, _ in page.events
        if event_action == action and (selector is None or event_selector == selector)
    )
