from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from smhelper.infrastructure.task_queue.celery.node_tasks import (
    CeleryTaskRegistry,
    register_node_browser_tasks,
)
from smhelper.infrastructure.task_queue.celery.tasks import (
    CHECK_SESSION_TASK,
    CLOSE_SESSION_TASK,
    ENTER_LIVE_ROOM_TASK,
    SEND_COMMENT_TASK,
)


@dataclass
class FakeCeleryTaskRegistry(CeleryTaskRegistry):
    tasks: dict[str, Callable[..., None]] = field(default_factory=dict)

    def task(
        self, *, name: str
    ) -> Callable[[Callable[..., None]], Callable[..., None]]:
        def register(func: Callable[..., None]) -> Callable[..., None]:
            self.tasks[name] = func
            return func

        return register


@dataclass
class FakeNodeHandler:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def enter_live_room(self, payload: object) -> None:
        self.calls.append(("enter", getattr(payload, "session_id")))

    def send_comment(self, payload: object) -> None:
        self.calls.append(("send", getattr(payload, "dispatch_job_id")))

    def close_session(self, payload: object) -> None:
        self.calls.append(("close", getattr(payload, "session_id")))

    def check_session(self, payload: object) -> None:
        self.calls.append(("check", getattr(payload, "session_id")))


def test_register_node_browser_tasks_builds_payloads_and_delegates_to_handler() -> None:
    app = FakeCeleryTaskRegistry()
    handler = FakeNodeHandler()

    register_node_browser_tasks(app=app, handler=handler)
    app.tasks[ENTER_LIVE_ROOM_TASK](
        session_id="session-1",
        account_id="account-1",
        live_task_id="live-1",
        room_url="https://example.com/live/1",
        platform="xhs",
    )
    app.tasks[SEND_COMMENT_TASK](
        dispatch_job_id="job-1",
        session_id="session-1",
        account_id="account-1",
        final_text="hello",
    )
    app.tasks[CHECK_SESSION_TASK](session_id="session-1")
    app.tasks[CLOSE_SESSION_TASK](session_id="session-1", reason="live_ended")

    assert handler.calls == [
        ("enter", "session-1"),
        ("send", "job-1"),
        ("check", "session-1"),
        ("close", "session-1"),
    ]
