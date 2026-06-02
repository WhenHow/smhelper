from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from sys import modules
from typing import Callable

from smhelper.infrastructure.task_queue.celery import center_runtime
from smhelper.infrastructure.task_queue.celery.center_worker_runtime import (
    CenterWorkerRuntime,
    build_center_worker_runtime,
)
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry
from smhelper.infrastructure.task_queue.celery.tasks import PROCESS_SEGMENT_TASK


@dataclass
class FakeCeleryApp(CeleryTaskRegistry):
    tasks: dict[str, Callable[..., None]] = field(default_factory=dict)

    def task(
        self,
        *,
        name: str,
    ) -> Callable[[Callable[..., None]], Callable[..., None]]:
        def register(func: Callable[..., None]) -> Callable[..., None]:
            self.tasks[name] = func
            return func

        return register


class FakeSegmentProcessor:
    def process_segment(
        self,
        *,
        segment_id: str,
        product_context: str,
        task_context: str,
    ) -> str | None:
        return None


def test_center_celery_worker_module_exposes_registered_celery_app(
    monkeypatch,
) -> None:
    fake_runtime = build_center_worker_runtime(
        segment_processor=FakeSegmentProcessor(),
        celery_app=FakeCeleryApp(),
    )

    def build_fake_runtime() -> CenterWorkerRuntime:
        return fake_runtime

    monkeypatch.setattr(
        center_runtime,
        "build_configured_center_worker_runtime",
        build_fake_runtime,
    )
    modules.pop("smhelper.infrastructure.task_queue.celery.center_worker", None)

    module = import_module("smhelper.infrastructure.task_queue.celery.center_worker")

    assert module.runtime is fake_runtime
    assert module.celery_app is fake_runtime.celery_app
    assert PROCESS_SEGMENT_TASK in module.celery_app.tasks
