"""Celery app entry point for center-side live processing workers.

Run a center worker with Celery's own CLI, for example:

    uv run celery -A smhelper.infrastructure.task_queue.celery.center_worker.celery_app \
      worker -Q center.live
"""

from __future__ import annotations

from smhelper.infrastructure.task_queue.celery.center_runtime import (
    build_configured_center_worker_runtime,
)
from smhelper.infrastructure.task_queue.celery.center_worker_runtime import (
    CenterWorkerRuntime,
)
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry

runtime: CenterWorkerRuntime = build_configured_center_worker_runtime()
celery_app: CeleryTaskRegistry = runtime.celery_app
