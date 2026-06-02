from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from smhelper.infrastructure.task_queue.celery.center_worker_runtime import (
    build_center_worker_runtime,
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


@dataclass
class FakeLiveTaskObserverRunner:
    observed_live_task_ids: list[str] = field(default_factory=list)

    def run_until_finished(self, *, live_task_id: str) -> object | None:
        self.observed_live_task_ids.append(live_task_id)
        return None


def test_build_center_worker_runtime_registers_center_tasks() -> None:
    celery_app = FakeCeleryApp()
    segment_processor = FakeSegmentProcessor()
    observer_runner = FakeLiveTaskObserverRunner()

    runtime = build_center_worker_runtime(
        celery_app=celery_app,
        segment_processor=segment_processor,
        live_task_observer_runner=observer_runner,
    )
    celery_app.tasks[PROCESS_SEGMENT_TASK](
        segment_id="segment-1",
        product_context="Face cream for oily skin.",
        task_context="Ask product-related questions.",
    )
    celery_app.tasks[OBSERVE_LIVE_TASK_TASK](live_task_id="live-1")

    assert runtime.celery_app is celery_app
    assert runtime.handler.segment_processor is segment_processor
    assert runtime.handler.live_task_observer_runner is observer_runner
    assert segment_processor.calls == [
        (
            "segment-1",
            "Face cream for oily skin.",
            "Ask product-related questions.",
        )
    ]
    assert observer_runner.observed_live_task_ids == ["live-1"]
