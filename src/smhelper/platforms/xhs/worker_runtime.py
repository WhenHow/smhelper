"""Xiaohongshu worker-node runtime wiring."""

from __future__ import annotations

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.task_queue.celery.node_handler import CenterApiClient
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry
from smhelper.infrastructure.task_queue.celery.node_worker_runtime import (
    NodeWorkerHeartbeat,
    NodeWorkerRuntime,
    build_node_worker_runtime,
)
from smhelper.platforms.xhs.browser.cloakbrowser_live_room import (
    XhsCloakBrowserLiveRoomSessionManager,
)
from smhelper.platforms.xhs.browser.live_room_operator import (
    XhsLiveRoomBrowserOperator,
    XhsLiveRoomSessionManager,
)


def build_xhs_node_worker_runtime(
    *,
    settings: RuntimeSettings | None = None,
    celery_app: CeleryTaskRegistry | None = None,
    center_api: CenterApiClient | None = None,
    session_manager: XhsLiveRoomSessionManager | None = None,
    node_id: str | None = None,
    queue_name: str | None = None,
    max_browser_sessions: int = 1,
) -> NodeWorkerRuntime:
    """Build a worker-node runtime for Xiaohongshu live-room browser actions."""
    resolved_session_manager = (
        session_manager or XhsCloakBrowserLiveRoomSessionManager()
    )
    heartbeat = None
    if node_id is not None:
        heartbeat = NodeWorkerHeartbeat(
            node_id=node_id,
            queue_name=queue_name or f"node.{node_id}.browser",
            supported_platforms=("xhs",),
            max_browser_sessions=max_browser_sessions,
        )
    return build_node_worker_runtime(
        settings=settings,
        celery_app=celery_app,
        center_api=center_api,
        heartbeat=heartbeat,
        browser_operator=XhsLiveRoomBrowserOperator(
            session_manager=resolved_session_manager,
        ),
    )
