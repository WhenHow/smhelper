from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ProcessSegmentPayload,
    register_center_tasks,
)
from smhelper.infrastructure.task_queue.celery.tasks import PROCESS_SEGMENT_TASK


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
    payloads: list[ProcessSegmentPayload] = field(default_factory=list)

    def process_segment(self, payload: ProcessSegmentPayload) -> None:
        self.payloads.append(payload)


def test_register_center_tasks_delegates_process_segment_payload() -> None:
    app = FakeCeleryApp()
    handler = FakeCenterTaskHandler()

    register_center_tasks(app=app, handler=handler)
    app.tasks[PROCESS_SEGMENT_TASK](
        segment_id="segment-1",
        product_context="Face cream for oily skin.",
        task_context="Ask product-related questions.",
    )

    assert set(app.tasks) == {PROCESS_SEGMENT_TASK}
    assert handler.payloads == [
        ProcessSegmentPayload(
            segment_id="segment-1",
            product_context="Face cream for oily skin.",
            task_context="Ask product-related questions.",
        )
    ]
