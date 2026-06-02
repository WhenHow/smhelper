from __future__ import annotations

from dataclasses import dataclass, field

from smhelper.infrastructure.task_queue.celery.app import create_celery_app
from smhelper.infrastructure.task_queue.celery.publisher import (
    BrowserTaskPublisher,
    CloseSessionPayload,
    EnterLiveRoomPayload,
    SendCommentPayload,
)
from smhelper.infrastructure.task_queue.celery.tasks import (
    CLOSE_SESSION_TASK,
    ENTER_LIVE_ROOM_TASK,
    SEND_COMMENT_TASK,
)


@dataclass
class FakeCeleryApp:
    calls: list[tuple[str, dict[str, str], str, int | None]] = field(
        default_factory=list
    )

    def send_task(
        self,
        name: str,
        *,
        kwargs: dict[str, str],
        queue: str,
        countdown: int | None = None,
    ) -> None:
        self.calls.append((name, kwargs, queue, countdown))


def test_create_celery_app_configures_broker_backend_and_json_serialization() -> None:
    app = create_celery_app(
        broker_url="redis://localhost:6379/0",
        result_backend_url="redis://localhost:6379/1",
    )

    assert app.conf.broker_url == "redis://localhost:6379/0"
    assert app.conf.result_backend == "redis://localhost:6379/1"
    assert app.conf.task_serializer == "json"
    assert app.conf.accept_content == ["json"]


def test_browser_task_publisher_sends_enter_room_payload_to_node_queue() -> None:
    celery_app = FakeCeleryApp()

    BrowserTaskPublisher(celery_app=celery_app).enter_live_room(
        queue_name="node.node-a.browser",
        payload=EnterLiveRoomPayload(
            session_id="session-1",
            account_id="account-1",
            live_task_id="live-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        ),
    )

    assert celery_app.calls == [
        (
            ENTER_LIVE_ROOM_TASK,
            {
                "session_id": "session-1",
                "account_id": "account-1",
                "live_task_id": "live-1",
                "room_url": "https://example.com/live/1",
                "platform": "xhs",
            },
            "node.node-a.browser",
            None,
        )
    ]


def test_browser_task_publisher_can_delay_enter_room_task() -> None:
    celery_app = FakeCeleryApp()

    BrowserTaskPublisher(celery_app=celery_app).enter_live_room(
        queue_name="node.node-a.browser",
        payload=EnterLiveRoomPayload(
            session_id="session-1",
            account_id="account-1",
            live_task_id="live-1",
            room_url="https://example.com/live/1",
            platform="xhs",
        ),
        countdown_seconds=17,
    )

    assert celery_app.calls == [
        (
            ENTER_LIVE_ROOM_TASK,
            {
                "session_id": "session-1",
                "account_id": "account-1",
                "live_task_id": "live-1",
                "room_url": "https://example.com/live/1",
                "platform": "xhs",
            },
            "node.node-a.browser",
            17,
        )
    ]


def test_browser_task_publisher_never_sends_storage_state_in_payload() -> None:
    celery_app = FakeCeleryApp()

    BrowserTaskPublisher(celery_app=celery_app).send_comment(
        queue_name="node.node-a.browser",
        payload=SendCommentPayload(
            dispatch_job_id="job-1",
            session_id="session-1",
            account_id="account-1",
            final_text="Is this suitable for oily skin?",
        ),
    )
    BrowserTaskPublisher(celery_app=celery_app).close_session(
        queue_name="node.node-a.browser",
        payload=CloseSessionPayload(session_id="session-1", reason="live_ended"),
    )

    for _, kwargs, _, _ in celery_app.calls:
        assert "storage_state" not in kwargs
        assert "storage_state_json" not in kwargs

    assert [call[0] for call in celery_app.calls] == [
        SEND_COMMENT_TASK,
        CLOSE_SESSION_TASK,
    ]
