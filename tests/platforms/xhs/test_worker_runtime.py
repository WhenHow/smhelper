from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from smhelper.infrastructure.task_queue.celery.node_handler import CenterApiClient
from smhelper.infrastructure.task_queue.celery.tasks import (
    CLOSE_SESSION_TASK,
    ENTER_LIVE_ROOM_TASK,
    SEND_COMMENT_TASK,
)
from smhelper.platforms.xhs.browser.cloakbrowser_live_room import (
    XhsCloakBrowserLiveRoomSessionManager,
)
from smhelper.platforms.xhs.browser.live_room_operator import (
    XhsLiveRoomBrowserOperator,
)
from smhelper.platforms.xhs.worker_runtime import build_xhs_node_worker_runtime


@dataclass
class FakeCeleryApp:
    tasks: dict[str, Callable[..., None]] = field(default_factory=dict)

    def task(
        self,
        *,
        name: str,
    ) -> Callable[[Callable[..., None]], Callable[..., None]]:
        def register(func: Callable[..., None]) -> Callable[..., None]:
            self.tasks[name] = func
            return func

        return register


@dataclass
class FakeCenterApiClient(CenterApiClient):
    storage_state_path: Path
    fetched: list[tuple[str, str]] = field(default_factory=list)
    session_reports: list[tuple[str, str, str | None]] = field(default_factory=list)
    send_reports: list[tuple[str, str, str, str, str | None]] = field(
        default_factory=list
    )

    def fetch_storage_state(self, *, account_id: str, platform: str) -> Path:
        self.fetched.append((account_id, platform))
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
class FakeLiveRoomSession:
    sent_comments: list[str] = field(default_factory=list)
    closed: bool = False

    def send_comment(self, text: str) -> None:
        self.sent_comments.append(text)

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeSessionManager:
    session: FakeLiveRoomSession
    opened: list[tuple[str, str, Path]] = field(default_factory=list)

    def open_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> FakeLiveRoomSession:
        self.opened.append((session_id, room_url, storage_state_path))
        return self.session


def test_xhs_node_worker_runtime_registers_tasks_with_xhs_operator(
    tmp_path: Path,
) -> None:
    celery_app = FakeCeleryApp()
    center_api = FakeCenterApiClient(storage_state_path=tmp_path / "storage_state.json")
    live_session = FakeLiveRoomSession()
    session_manager = FakeSessionManager(session=live_session)

    runtime = build_xhs_node_worker_runtime(
        celery_app=celery_app,
        center_api=center_api,
        session_manager=session_manager,
    )
    celery_app.tasks[ENTER_LIVE_ROOM_TASK](
        session_id="session-1",
        account_id="account-1",
        live_task_id="live-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        platform="xhs",
    )
    celery_app.tasks[SEND_COMMENT_TASK](
        dispatch_job_id="dispatch-1",
        session_id="session-1",
        account_id="account-1",
        final_text="Is this suitable for oily skin?",
    )
    celery_app.tasks[CLOSE_SESSION_TASK](session_id="session-1", reason="live ended")

    assert isinstance(runtime.handler.browser_operator, XhsLiveRoomBrowserOperator)
    assert center_api.fetched == [("account-1", "xhs")]
    assert session_manager.opened == [
        (
            "session-1",
            "https://www.xiaohongshu.com/livestream/1",
            tmp_path / "storage_state.json",
        )
    ]
    assert center_api.session_reports == [
        ("session-1", "waiting", None),
        ("session-1", "closed", None),
    ]
    assert center_api.send_reports == [
        ("dispatch-1", "session-1", "account-1", "success", None)
    ]
    assert live_session.sent_comments == ["Is this suitable for oily skin?"]
    assert live_session.closed is True


def test_xhs_node_worker_runtime_uses_cloakbrowser_session_manager_by_default() -> None:
    celery_app = FakeCeleryApp()
    center_api = FakeCenterApiClient(storage_state_path=Path("storage_state.json"))

    runtime = build_xhs_node_worker_runtime(
        celery_app=celery_app,
        center_api=center_api,
    )

    assert isinstance(runtime.handler.browser_operator, XhsLiveRoomBrowserOperator)
    assert isinstance(
        runtime.handler.browser_operator.session_manager,
        XhsCloakBrowserLiveRoomSessionManager,
    )
    assert set(celery_app.tasks) == {
        ENTER_LIVE_ROOM_TASK,
        SEND_COMMENT_TASK,
        CLOSE_SESSION_TASK,
    }
