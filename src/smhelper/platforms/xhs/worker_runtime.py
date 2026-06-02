"""Xiaohongshu worker-node runtime wiring."""

from __future__ import annotations

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.task_queue.celery.node_handler import CenterApiClient
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry
from smhelper.infrastructure.task_queue.celery.node_worker_runtime import (
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
) -> NodeWorkerRuntime:
    """Build a worker-node runtime for Xiaohongshu live-room browser actions."""
    resolved_session_manager = (
        session_manager or XhsCloakBrowserLiveRoomSessionManager()
    )
    return build_node_worker_runtime(
        settings=settings,
        celery_app=celery_app,
        center_api=center_api,
        browser_operator=XhsLiveRoomBrowserOperator(
            session_manager=resolved_session_manager,
        ),
    )
