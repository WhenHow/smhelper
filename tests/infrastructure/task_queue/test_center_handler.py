from __future__ import annotations

from dataclasses import dataclass, field

from smhelper.infrastructure.task_queue.celery.center_handler import CenterTaskHandler
from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ObserveLiveTaskPayload,
    ProcessSegmentPayload,
)


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

    def run_once(self, *, live_task_id: str) -> object | None:
        self.observed_live_task_ids.append(live_task_id)
        return None


def test_center_handler_processes_segments() -> None:
    segment_processor = FakeSegmentProcessor()
    observer_runner = FakeLiveTaskObserverRunner()

    CenterTaskHandler(
        segment_processor=segment_processor,
        live_task_observer_runner=observer_runner,
    ).process_segment(
        ProcessSegmentPayload(
            segment_id="segment-1",
            product_context="Face cream.",
            task_context="Ask product questions.",
        )
    )

    assert segment_processor.calls == [
        ("segment-1", "Face cream.", "Ask product questions.")
    ]
    assert observer_runner.observed_live_task_ids == []


def test_center_handler_observes_live_tasks() -> None:
    segment_processor = FakeSegmentProcessor()
    observer_runner = FakeLiveTaskObserverRunner()

    CenterTaskHandler(
        segment_processor=segment_processor,
        live_task_observer_runner=observer_runner,
    ).observe_live_task(ObserveLiveTaskPayload(live_task_id="live-1"))

    assert observer_runner.observed_live_task_ids == ["live-1"]
    assert segment_processor.calls == []
