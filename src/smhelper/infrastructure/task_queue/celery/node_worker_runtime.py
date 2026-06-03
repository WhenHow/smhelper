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
class NodeWorkerHeartbeat:
    """Worker-node metadata reported to the center scheduler."""

    node_id: str
    queue_name: str
    supported_platforms: tuple[str, ...]
    max_browser_sessions: int
    active_browser_sessions: int = 0


@dataclass(frozen=True, slots=True)
class NodeWorkerRuntime:
    """Assembled worker-node runtime objects."""

    celery_app: CeleryTaskRegistry
    handler: NodeBrowserTaskHandler
    heartbeat: NodeWorkerHeartbeat | None = None

    def report_heartbeat(self) -> bool:
        """Report this worker node to the center when heartbeat metadata exists."""
        if self.heartbeat is None:
            return False
        self.handler.center_api.report_worker_heartbeat(
            node_id=self.heartbeat.node_id,
            queue_name=self.heartbeat.queue_name,
            supported_platforms=list(self.heartbeat.supported_platforms),
            max_browser_sessions=self.heartbeat.max_browser_sessions,
            active_browser_sessions=self.heartbeat.active_browser_sessions,
        )
        return True


def build_node_worker_runtime(
    *,
    browser_operator: LiveRoomBrowserOperator,
    settings: RuntimeSettings | None = None,
    celery_app: CeleryTaskRegistry | None = None,
    center_api: CenterApiClient | None = None,
    heartbeat: NodeWorkerHeartbeat | None = None,
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
    return NodeWorkerRuntime(
        celery_app=resolved_celery_app,
        handler=handler,
        heartbeat=heartbeat,
    )
