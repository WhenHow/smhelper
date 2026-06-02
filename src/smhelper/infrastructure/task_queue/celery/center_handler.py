"""Center-side Celery task handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from smhelper.infrastructure.task_queue.celery.center_tasks import (
    ProcessSegmentPayload,
)


class SegmentProcessor(Protocol):
    """Persistence-backed processor for completed live segments."""

    def process_segment(
        self,
        *,
        segment_id: str,
        product_context: str,
        task_context: str,
    ) -> str | None:
        """Process one segment and return the generated candidate id if any."""


@dataclass(frozen=True, slots=True)
class CenterTaskHandler:
    """Coordinates center-side asynchronous processing tasks."""

    segment_processor: SegmentProcessor

    def process_segment(self, payload: ProcessSegmentPayload) -> None:
        """Process a completed live segment."""
        self.segment_processor.process_segment(
            segment_id=payload.segment_id,
            product_context=payload.product_context,
            task_context=payload.task_context,
        )
