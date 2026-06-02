"""Celery app entry point for Xiaohongshu browser-operation worker nodes.

Run a node worker with Celery's own CLI, for example:

    uv run celery -A smhelper.platforms.xhs.celery_worker.celery_app worker \
      -Q node.<node_id>.browser
"""

from __future__ import annotations

from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry
from smhelper.infrastructure.task_queue.celery.node_worker_runtime import (
    NodeWorkerRuntime,
)
from smhelper.platforms.xhs.worker_runtime import build_xhs_node_worker_runtime

runtime: NodeWorkerRuntime = build_xhs_node_worker_runtime()
celery_app: CeleryTaskRegistry = runtime.celery_app
