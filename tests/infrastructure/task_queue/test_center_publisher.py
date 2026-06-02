from __future__ import annotations

from dataclasses import dataclass, field

from smhelper.infrastructure.task_queue.celery.center_publisher import (
    CenterTaskPublisher,
)
from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ObserveLiveTaskPayload,
    ProcessSegmentPayload,
)
from smhelper.infrastructure.task_queue.celery.tasks import (
    OBSERVE_LIVE_TASK_TASK,
    PROCESS_SEGMENT_TASK,
)


@dataclass
class FakeCeleryTaskSender:
    sent: list[tuple[str, dict[str, str], str, int | None]] = field(
        default_factory=list
    )

    def send_task(
        self,
        name: str,
        *,
        kwargs: dict[str, str],
        queue: str,
        countdown: int | None = None,
    ) -> object:
        self.sent.append((name, kwargs, queue, countdown))
        return None


def test_center_task_publisher_sends_process_segment_to_center_queue() -> None:
    celery_app = FakeCeleryTaskSender()

    CenterTaskPublisher(celery_app=celery_app).process_segment(
        queue_name="center.live",
        payload=ProcessSegmentPayload(
            segment_id="segment-1",
            product_context="Face cream for oily skin.",
            task_context="Ask product-related questions.",
        ),
    )

    assert celery_app.sent == [
        (
            PROCESS_SEGMENT_TASK,
            {
                "segment_id": "segment-1",
                "product_context": "Face cream for oily skin.",
                "task_context": "Ask product-related questions.",
            },
            "center.live",
            None,
        )
    ]


def test_center_task_publisher_sends_observe_live_task_to_center_queue() -> None:
    celery_app = FakeCeleryTaskSender()

    CenterTaskPublisher(celery_app=celery_app).observe_live_task(
        queue_name="center.live",
        payload=ObserveLiveTaskPayload(live_task_id="live-1"),
    )

    assert celery_app.sent == [
        (
            OBSERVE_LIVE_TASK_TASK,
            {"live_task_id": "live-1"},
            "center.live",
            None,
        )
    ]
