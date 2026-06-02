from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from smhelper.infrastructure.task_queue.celery.center_worker_runtime import (
    build_center_worker_runtime,
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
class FakeSegmentProcessor:
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def process_segment(
        self,
        *,
        segment_id: str,
        product_context: str,
        task_context: str,
    ) -> str | None:
        self.calls.append((segment_id, product_context, task_context))
        return "candidate-1"


def test_build_center_worker_runtime_registers_process_segment_task() -> None:
    celery_app = FakeCeleryApp()
    segment_processor = FakeSegmentProcessor()

    runtime = build_center_worker_runtime(
        celery_app=celery_app,
        segment_processor=segment_processor,
    )
    celery_app.tasks[PROCESS_SEGMENT_TASK](
        segment_id="segment-1",
        product_context="Face cream for oily skin.",
        task_context="Ask product-related questions.",
    )

    assert runtime.celery_app is celery_app
    assert runtime.handler.segment_processor is segment_processor
    assert segment_processor.calls == [
        (
            "segment-1",
            "Face cream for oily skin.",
            "Ask product-related questions.",
        )
    ]
