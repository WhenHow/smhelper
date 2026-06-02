"""Celery publisher for center-side live processing tasks."""

from __future__ import annotations

from dataclasses import dataclass

from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ProcessSegmentPayload,
)
from smhelper.infrastructure.task_queue.celery.publisher import CeleryTaskSender
from smhelper.infrastructure.task_queue.celery.tasks import PROCESS_SEGMENT_TASK


@dataclass(frozen=True, slots=True)
class CenterTaskPublisher:
    """Publishes center-side processing tasks to Celery queues."""

    celery_app: CeleryTaskSender

    def process_segment(
        self,
        *,
        queue_name: str,
        payload: ProcessSegmentPayload,
    ) -> None:
        """Publish a completed-segment processing task."""
        self.celery_app.send_task(
            PROCESS_SEGMENT_TASK,
            kwargs=payload.to_kwargs(),
            queue=queue_name,
        )
