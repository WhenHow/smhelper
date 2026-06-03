from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from smhelper.infrastructure.task_queue.celery.node_handler import (
    BrowserActionResult,
    CenterApiClient,
    LiveRoomBrowserOperator,
    NodeBrowserTaskHandler,
)
from smhelper.infrastructure.task_queue.celery.publisher import (
    CheckSessionPayload,
    CloseSessionPayload,
    EnterLiveRoomPayload,
    SendCommentPayload,
)


@dataclass
class FakeCenterApiClient(CenterApiClient):
    storage_state_path: Path
    fetch_error: Exception | None = None
    fetched: list[tuple[str, str]] = field(default_factory=list)
    session_reports: list[tuple[str, str, str | None]] = field(default_factory=list)
    send_reports: list[tuple[str, str, str, str, str | None]] = field(
        default_factory=list
    )

    def fetch_storage_state(self, *, account_id: str, platform: str) -> Path:
        self.fetched.append((account_id, platform))
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.storage_state_path

    def report_session_status(
        self,
        *,
        session_id: str,
        status: str,
        failure_reason: str | None,
    ) -> None:
        self.session_reports.append((session_id, status, failure_reason))

    def report_send_result(
        self,
        *,
        dispatch_job_id: str,
        session_id: str,
        account_id: str,
        status: str,
        failure_reason: str | None,
    ) -> None:
        self.send_reports.append(
            (dispatch_job_id, session_id, account_id, status, failure_reason)
        )


@dataclass
class FakeBrowserOperator(LiveRoomBrowserOperator):
    result: BrowserActionResult
    enter_error: Exception | None = None
    send_error: Exception | None = None
    close_error: Exception | None = None
    entered: list[tuple[str, str, Path]] = field(default_factory=list)
    sent: list[tuple[str, str]] = field(default_factory=list)
    closed: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    def enter_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> BrowserActionResult:
        self.entered.append((session_id, room_url, storage_state_path))
        if self.enter_error is not None:
            raise self.enter_error
        return self.result

    def send_comment(self, *, session_id: str, final_text: str) -> BrowserActionResult:
        self.sent.append((session_id, final_text))
        if self.send_error is not None:
            raise self.send_error
        return self.result

    def close_session(self, *, session_id: str) -> BrowserActionResult:
        self.closed.append(session_id)
        if self.close_error is not None:
            raise self.close_error
        return self.result

    def check_session(self, *, session_id: str) -> BrowserActionResult:
        self.checked.append(session_id)
        return self.result


def test_node_handler_fetches_storage_state_enters_room_and_reports_waiting(
    tmp_path: Path,
) -> None:
    storage_state_path = tmp_path / "storage_state.json"
    center = FakeCenterApiClient(storage_state_path=storage_state_path)
    browser = FakeBrowserOperator(result=BrowserActionResult(success=True))

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).enter_live_room(
        EnterLiveRoomPayload(
            session_id="session-1",
            account_id="account-1",
            live_task_id="live-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        )
    )

    assert center.fetched == [("account-1", "xhs")]
    assert browser.entered == [
        ("session-1", "https://example.com/live/1", storage_state_path)
    ]
    assert center.session_reports == [("session-1", "waiting", None)]


def test_node_handler_reports_send_result_after_browser_send() -> None:
    center = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))
    browser = FakeBrowserOperator(result=BrowserActionResult(success=True))

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).send_comment(
        SendCommentPayload(
            dispatch_job_id="job-1",
            session_id="session-1",
            account_id="account-1",
            final_text="Is this suitable for oily skin?",
        )
    )

    assert browser.sent == [("session-1", "Is this suitable for oily skin?")]
    assert center.send_reports == [("job-1", "session-1", "account-1", "success", None)]


def test_node_handler_reports_closed_after_browser_close() -> None:
    center = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))
    browser = FakeBrowserOperator(result=BrowserActionResult(success=True))

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).close_session(
        CloseSessionPayload(session_id="session-1", reason="live_ended")
    )

    assert browser.closed == ["session-1"]
    assert center.session_reports == [("session-1", "closed", None)]


def test_node_handler_reports_waiting_after_browser_session_health_check() -> None:
    center = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))
    browser = FakeBrowserOperator(result=BrowserActionResult(success=True))

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).check_session(
        CheckSessionPayload(session_id="session-1")
    )

    assert browser.checked == ["session-1"]
    assert center.session_reports == [("session-1", "waiting", None)]


def test_node_handler_reports_lost_when_browser_session_health_check_fails() -> None:
    center = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))
    browser = FakeBrowserOperator(
        result=BrowserActionResult(success=False, failure_reason="page closed")
    )

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).check_session(
        CheckSessionPayload(session_id="session-1")
    )

    assert center.session_reports == [("session-1", "lost", "page closed")]


def test_node_handler_reports_failed_when_storage_state_fetch_fails() -> None:
    center = FakeCenterApiClient(
        storage_state_path=Path("storage_state.json"),
        fetch_error=RuntimeError("storage state not found"),
    )
    browser = FakeBrowserOperator(result=BrowserActionResult(success=True))

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).enter_live_room(
        EnterLiveRoomPayload(
            session_id="session-1",
            account_id="account-1",
            live_task_id="live-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        )
    )

    assert browser.entered == []
    assert center.session_reports == [
        ("session-1", "failed", "storage state not found")
    ]


def test_node_handler_reports_failed_when_enter_room_raises() -> None:
    center = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))
    browser = FakeBrowserOperator(
        result=BrowserActionResult(success=True),
        enter_error=RuntimeError("browser crashed"),
    )

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).enter_live_room(
        EnterLiveRoomPayload(
            session_id="session-1",
            account_id="account-1",
            live_task_id="live-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        )
    )

    assert center.session_reports == [("session-1", "failed", "browser crashed")]


def test_node_handler_reports_failed_when_send_raises() -> None:
    center = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))
    browser = FakeBrowserOperator(
        result=BrowserActionResult(success=True),
        send_error=RuntimeError("input not found"),
    )

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).send_comment(
        SendCommentPayload(
            dispatch_job_id="job-1",
            session_id="session-1",
            account_id="account-1",
            final_text="Is this suitable for oily skin?",
        )
    )

    assert center.send_reports == [
        ("job-1", "session-1", "account-1", "failed", "input not found")
    ]


def test_node_handler_reports_lost_when_close_raises() -> None:
    center = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))
    browser = FakeBrowserOperator(
        result=BrowserActionResult(success=True),
        close_error=RuntimeError("browser already gone"),
    )

    NodeBrowserTaskHandler(center_api=center, browser_operator=browser).close_session(
        CloseSessionPayload(session_id="session-1", reason="live_ended")
    )

    assert center.session_reports == [("session-1", "lost", "browser already gone")]
