"""Runtime wiring for center-side Celery processing workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.task_queue.celery.app import create_celery_app
from smhelper.infrastructure.task_queue.celery.center_handler import (
    CenterTaskHandler,
    LiveTaskObserverRunner,
    SegmentProcessor,
)
from smhelper.infrastructure.task_queue.celery.center_tasks import (
    register_center_tasks,
)
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry


@dataclass(frozen=True, slots=True)
class CenterWorkerRuntime:
    """Assembled center worker runtime objects."""

    celery_app: CeleryTaskRegistry
    handler: CenterTaskHandler


def build_center_worker_runtime(
    *,
    segment_processor: SegmentProcessor,
    live_task_observer_runner: LiveTaskObserverRunner,
    settings: RuntimeSettings | None = None,
    celery_app: CeleryTaskRegistry | None = None,
) -> CenterWorkerRuntime:
    """Build and register a center-side Celery worker runtime."""
    resolved_settings = settings or RuntimeSettings.from_env()
    resolved_celery_app = celery_app or cast(
        CeleryTaskRegistry,
        create_celery_app(
            broker_url=resolved_settings.celery_broker_url,
            result_backend_url=resolved_settings.celery_result_backend_url,
        ),
    )
    handler = CenterTaskHandler(
        segment_processor=segment_processor,
        live_task_observer_runner=live_task_observer_runner,
    )
    register_center_tasks(app=resolved_celery_app, handler=handler)
    return CenterWorkerRuntime(celery_app=resolved_celery_app, handler=handler)
