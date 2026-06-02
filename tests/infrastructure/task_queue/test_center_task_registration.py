from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ObserveLiveTaskPayload,
    ProcessSegmentPayload,
    register_center_tasks,
)
from smhelper.infrastructure.task_queue.celery.tasks import (
    OBSERVE_LIVE_TASK_TASK,
    PROCESS_SEGMENT_TASK,
)


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
class FakeCenterTaskHandler:
    segment_payloads: list[ProcessSegmentPayload] = field(default_factory=list)
    observation_payloads: list[ObserveLiveTaskPayload] = field(default_factory=list)

    def process_segment(self, payload: ProcessSegmentPayload) -> None:
        self.segment_payloads.append(payload)

    def observe_live_task(self, payload: ObserveLiveTaskPayload) -> None:
        self.observation_payloads.append(payload)


def test_register_center_tasks_delegates_process_segment_payload() -> None:
    app = FakeCeleryApp()
    handler = FakeCenterTaskHandler()

    register_center_tasks(app=app, handler=handler)
    app.tasks[PROCESS_SEGMENT_TASK](
        segment_id="segment-1",
        product_context="Face cream for oily skin.",
        task_context="Ask product-related questions.",
    )

    assert set(app.tasks) == {PROCESS_SEGMENT_TASK, OBSERVE_LIVE_TASK_TASK}
    assert handler.segment_payloads == [
        ProcessSegmentPayload(
            segment_id="segment-1",
            product_context="Face cream for oily skin.",
            task_context="Ask product-related questions.",
        )
    ]


def test_register_center_tasks_delegates_observe_live_task_payload() -> None:
    app = FakeCeleryApp()
    handler = FakeCenterTaskHandler()

    register_center_tasks(app=app, handler=handler)
    app.tasks[OBSERVE_LIVE_TASK_TASK](live_task_id="live-1")

    assert handler.observation_payloads == [
        ObserveLiveTaskPayload(live_task_id="live-1")
    ]
