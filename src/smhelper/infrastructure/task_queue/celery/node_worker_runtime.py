"""Runtime wiring for browser-operation Celery worker nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.task_queue.celery.app import create_celery_app
from smhelper.infrastructure.task_queue.celery.center_api_client import (
    HttpCenterApiClient,
)
from smhelper.infrastructure.task_queue.celery.node_handler import (
    CenterApiClient,
    LiveRoomBrowserOperator,
    NodeBrowserTaskHandler,
)
from smhelper.infrastructure.task_queue.celery.node_tasks import (
    CeleryTaskRegistry,
    register_node_browser_tasks,
)


@dataclass(frozen=True, slots=True)
class NodeWorkerRuntime:
    """Assembled worker-node runtime objects."""

    celery_app: CeleryTaskRegistry
    handler: NodeBrowserTaskHandler


def build_node_worker_runtime(
    *,
    browser_operator: LiveRoomBrowserOperator,
    settings: RuntimeSettings | None = None,
    celery_app: CeleryTaskRegistry | None = None,
    center_api: CenterApiClient | None = None,
) -> NodeWorkerRuntime:
    """Build and register a browser-operation worker-node runtime."""
    resolved_settings = settings or RuntimeSettings.from_env()
    resolved_celery_app = celery_app or cast(
        CeleryTaskRegistry,
        create_celery_app(
            broker_url=resolved_settings.celery_broker_url,
            result_backend_url=resolved_settings.celery_result_backend_url,
        ),
    )
    resolved_center_api = center_api or HttpCenterApiClient(
        base_url=resolved_settings.center_api_url,
        storage_state_dir=resolved_settings.worker_storage_state_dir,
    )
    handler = NodeBrowserTaskHandler(
        center_api=resolved_center_api,
        browser_operator=browser_operator,
    )
    register_node_browser_tasks(app=resolved_celery_app, handler=handler)
    return NodeWorkerRuntime(celery_app=resolved_celery_app, handler=handler)
