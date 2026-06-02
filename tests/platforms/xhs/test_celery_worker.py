from __future__ import annotations

from importlib import import_module

from smhelper.infrastructure.task_queue.celery.node_worker_runtime import (
    NodeWorkerRuntime,
)
from smhelper.infrastructure.task_queue.celery.tasks import (
    CLOSE_SESSION_TASK,
    ENTER_LIVE_ROOM_TASK,
    SEND_COMMENT_TASK,
)


def test_xhs_celery_worker_module_exposes_registered_celery_app() -> None:
    module = import_module("smhelper.platforms.xhs.celery_worker")

    assert isinstance(module.runtime, NodeWorkerRuntime)
    assert module.celery_app is module.runtime.celery_app
    assert {
        ENTER_LIVE_ROOM_TASK,
        SEND_COMMENT_TASK,
        CLOSE_SESSION_TASK,
    }.issubset(module.celery_app.tasks)
