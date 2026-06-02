"""Celery task registration for center-side live processing operations."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Protocol

from smhelper.infrastructure.task_queue.celery.node_tasks import (
    CeleryTaskRegistry,
)
from smhelper.infrastructure.task_queue.celery.tasks import PROCESS_SEGMENT_TASK


@dataclass(frozen=True, slots=True)
class ProcessSegmentPayload:
    """Payload for processing one completed live segment."""

    segment_id: str
    product_context: str
    task_context: str

    def to_kwargs(self) -> dict[str, str]:
        """Serialize the payload for Celery JSON transport."""
        return asdict(self)


class CenterTaskHandler(Protocol):
    """Handler surface consumed by registered center Celery tasks."""

    def process_segment(self, payload: ProcessSegmentPayload) -> None:
        """Handle a completed-segment processing task."""


def register_center_tasks(
    *,
    app: CeleryTaskRegistry,
    handler: CenterTaskHandler,
) -> None:
    """Register center-side Celery tasks and delegate to the provided handler."""

    @app.task(name=PROCESS_SEGMENT_TASK)
    def process_segment(
        *,
        segment_id: str,
        product_context: str,
        task_context: str,
    ) -> None:
        handler.process_segment(
            ProcessSegmentPayload(
                segment_id=segment_id,
                product_context=product_context,
                task_context=task_context,
            )
        )
