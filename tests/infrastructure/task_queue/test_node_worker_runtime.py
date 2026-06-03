from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.task_queue.celery.center_api_client import (
    HttpCenterApiClient,
)
from smhelper.infrastructure.task_queue.celery.node_handler import (
    BrowserActionResult,
    CenterApiClient,
    LiveRoomBrowserOperator,
)
from smhelper.infrastructure.task_queue.celery.node_worker_runtime import (
    NodeWorkerHeartbeat,
    build_node_worker_runtime,
)
from smhelper.infrastructure.task_queue.celery.publisher import (
    EnterLiveRoomPayload,
)
from smhelper.infrastructure.task_queue.celery.tasks import ENTER_LIVE_ROOM_TASK
from smhelper.infrastructure.task_queue.celery.tasks import CHECK_SESSION_TASK
from smhelper.infrastructure.task_queue.celery.tasks import CLOSE_SESSION_TASK
from smhelper.infrastructure.task_queue.celery.tasks import SEND_COMMENT_TASK


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
    heartbeats: list[tuple[str, str, tuple[str, ...], int, int]] = field(
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
        raise AssertionError(
            f"unexpected send result: {dispatch_job_id} {session_id} {account_id} "
            f"{status} {failure_reason}"
        )

    def report_worker_heartbeat(
        self,
        *,
        node_id: str,
        queue_name: str,
        supported_platforms: list[str],
        max_browser_sessions: int,
        active_browser_sessions: int,
    ) -> None:
        self.heartbeats.append(
            (
                node_id,
                queue_name,
                tuple(supported_platforms),
                max_browser_sessions,
                active_browser_sessions,
            )
        )


@dataclass
class FakeBrowserOperator(LiveRoomBrowserOperator):
    entered: list[tuple[str, str, Path]] = field(default_factory=list)

    def enter_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> BrowserActionResult:
        self.entered.append((session_id, room_url, storage_state_path))
        return BrowserActionResult(success=True)

    def send_comment(self, *, session_id: str, final_text: str) -> BrowserActionResult:
        raise AssertionError(f"unexpected send: {session_id} {final_text}")

    def close_session(self, *, session_id: str) -> BrowserActionResult:
        raise AssertionError(f"unexpected close: {session_id}")


def test_build_node_worker_runtime_registers_node_tasks_and_wires_handler(
    tmp_path: Path,
) -> None:
    celery_app = FakeCeleryApp()
    center_api = FakeCenterApiClient(storage_state_path=tmp_path / "storage_state.json")
    browser_operator = FakeBrowserOperator()

    runtime = build_node_worker_runtime(
        celery_app=celery_app,
        center_api=center_api,
        browser_operator=browser_operator,
    )
    celery_app.tasks[ENTER_LIVE_ROOM_TASK](
        session_id="session-1",
        account_id="account-1",
        live_task_id="live-1",
        room_url="https://example.com/live/1",
        platform="xhs",
    )

    assert runtime.celery_app is celery_app
    assert runtime.handler.center_api is center_api
    assert runtime.handler.browser_operator is browser_operator
    assert center_api.fetched == [("account-1", "xhs")]
    assert browser_operator.entered == [
        ("session-1", "https://example.com/live/1", tmp_path / "storage_state.json")
    ]
    assert center_api.session_reports == [("session-1", "waiting", None)]


def test_build_node_worker_runtime_creates_http_center_client_from_settings(
    tmp_path: Path,
) -> None:
    celery_app = FakeCeleryApp()
    settings = RuntimeSettings.from_env(
        {
            "SMHELPER_CENTER_API_URL": "https://center.example",
            "SMHELPER_WORKER_STORAGE_STATE_DIR": str(tmp_path / "states"),
        },
        cwd=tmp_path,
    )

    runtime = build_node_worker_runtime(
        celery_app=celery_app,
        settings=settings,
        browser_operator=FakeBrowserOperator(),
    )

    assert isinstance(runtime.handler.center_api, HttpCenterApiClient)
    assert runtime.handler.center_api.base_url == "https://center.example"
    assert runtime.handler.center_api.storage_state_dir == tmp_path / "states"
    assert set(celery_app.tasks) == {
        ENTER_LIVE_ROOM_TASK,
        SEND_COMMENT_TASK,
        CHECK_SESSION_TASK,
        CLOSE_SESSION_TASK,
    }


def test_node_worker_runtime_builds_handler_from_existing_payload_type(
    tmp_path: Path,
) -> None:
    celery_app = FakeCeleryApp()
    center_api = FakeCenterApiClient(storage_state_path=tmp_path / "storage_state.json")
    browser_operator = FakeBrowserOperator()

    runtime = build_node_worker_runtime(
        celery_app=celery_app,
        center_api=center_api,
        browser_operator=browser_operator,
    )
    runtime.handler.enter_live_room(
        EnterLiveRoomPayload(
            session_id="session-1",
            account_id="account-1",
            live_task_id="live-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        )
    )

    assert center_api.session_reports == [("session-1", "waiting", None)]


def test_node_worker_runtime_reports_configured_worker_heartbeat(
    tmp_path: Path,
) -> None:
    celery_app = FakeCeleryApp()
    center_api = FakeCenterApiClient(storage_state_path=tmp_path / "storage_state.json")

    runtime = build_node_worker_runtime(
        celery_app=celery_app,
        center_api=center_api,
        browser_operator=FakeBrowserOperator(),
        heartbeat=NodeWorkerHeartbeat(
            node_id="node-1",
            queue_name="node.node-1.browser",
            supported_platforms=["xhs"],
            max_browser_sessions=4,
            active_browser_sessions=2,
        ),
    )

    runtime.report_heartbeat()

    assert center_api.heartbeats == [("node-1", "node.node-1.browser", ("xhs",), 4, 2)]
