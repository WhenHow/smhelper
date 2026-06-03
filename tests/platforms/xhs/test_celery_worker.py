from __future__ import annotations

from importlib import import_module
from importlib import reload

import pytest

from smhelper.infrastructure.task_queue.celery.node_worker_runtime import (
    NodeWorkerHeartbeat,
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


def test_xhs_celery_worker_module_uses_worker_env_for_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMHELPER_WORKER_NODE_ID", "node-env")
    monkeypatch.setenv("SMHELPER_WORKER_QUEUE_NAME", "node.env.browser")
    monkeypatch.setenv("SMHELPER_WORKER_MAX_BROWSER_SESSIONS", "5")

    module = reload(import_module("smhelper.platforms.xhs.celery_worker"))

    assert module.runtime.heartbeat == NodeWorkerHeartbeat(
        node_id="node-env",
        queue_name="node.env.browser",
        supported_platforms=("xhs",),
        max_browser_sessions=5,
    )


def test_xhs_celery_worker_reports_heartbeat_when_worker_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("smhelper.platforms.xhs.celery_worker")

    class FakeRuntime:
        reports = 0

        def report_heartbeat(self) -> bool:
            self.reports += 1
            return True

    fake_runtime = FakeRuntime()
    monkeypatch.setattr(module, "runtime", fake_runtime)

    module.report_heartbeat_when_worker_is_ready(sender=object())

    assert fake_runtime.reports == 1
