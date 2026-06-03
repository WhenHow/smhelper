"""Celery app entry point for Xiaohongshu browser-operation worker nodes.

Run a node worker with Celery's own CLI, for example:

    uv run celery -A smhelper.platforms.xhs.celery_worker.celery_app worker \
      -Q node.<node_id>.browser
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Protocol, cast

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry
from smhelper.infrastructure.task_queue.celery.node_worker_runtime import (
    NodeWorkerRuntime,
)
from smhelper.platforms.xhs.worker_runtime import build_xhs_node_worker_runtime


class CelerySignal(Protocol):
    """Celery signal surface used by this worker entry point."""

    def connect(self, receiver: Callable[..., object]) -> Callable[..., object]:
        """Register a signal receiver."""


settings = RuntimeSettings.from_env()
runtime: NodeWorkerRuntime = build_xhs_node_worker_runtime(
    settings=settings,
    node_id=settings.worker_node_id,
    queue_name=settings.worker_queue_name,
    max_browser_sessions=settings.worker_max_browser_sessions,
)
celery_app: CeleryTaskRegistry = runtime.celery_app


def report_heartbeat_when_worker_is_ready(**_: object) -> None:
    """Register or refresh this node once the Celery worker is ready."""
    runtime.report_heartbeat()


worker_ready = cast(
    CelerySignal,
    getattr(import_module("celery.signals"), "worker_ready"),
)
worker_ready.connect(report_heartbeat_when_worker_is_ready)
