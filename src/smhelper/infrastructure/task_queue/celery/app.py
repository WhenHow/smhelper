"""Celery application factory."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast


class CeleryConfig(Protocol):
    """Configuration surface used by this project."""

    broker_url: str
    result_backend: str | None
    task_serializer: str
    accept_content: list[str]

    def update(self, **kwargs: object) -> None:
        """Update Celery configuration values."""


class CeleryApplication(Protocol):
    """Runtime Celery application surface used by tests and publishers."""

    conf: CeleryConfig

    def send_task(self, name: str, *, kwargs: dict[str, str], queue: str) -> object:
        """Send a task to a named queue."""


class CeleryFactory(Protocol):
    """Callable constructor exposed by the celery package."""

    def __call__(
        self,
        main: str,
        *,
        broker: str,
        backend: str | None,
    ) -> CeleryApplication:
        """Create a Celery application."""


def create_celery_app(
    *,
    broker_url: str,
    result_backend_url: str | None = None,
) -> CeleryApplication:
    """Create a Celery app using JSON-only serialization."""
    celery_factory = cast(CeleryFactory, getattr(import_module("celery"), "Celery"))
    app = celery_factory("smhelper", broker=broker_url, backend=result_backend_url)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Shanghai",
        enable_utc=True,
    )
    return app
