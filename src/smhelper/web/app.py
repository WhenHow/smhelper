"""FastAPI application factory for smhelper management backend."""

from __future__ import annotations

from os import getenv
from random import Random

from fastapi import FastAPI
from sqlalchemy import Engine

from smhelper.core.clock import Clock, SystemClock
from smhelper.core.ids import IdGenerator, UuidGenerator
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.candidate_dispatcher import (
    SendCommentTaskPublisher,
    SqlAlchemyCandidateDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.task_queue.celery.app import create_celery_app
from smhelper.infrastructure.task_queue.celery.publisher import BrowserTaskPublisher
from smhelper.live.domain.policies.send_account_policy import SendAccountPolicy
from smhelper.web.api import router as api_router
from smhelper.web.admin import AdminCredentials, configure_admin


def create_app(
    *,
    database_url: str = "sqlite+pysqlite:///data/smhelper.db",
    engine: Engine | None = None,
    admin_credentials: AdminCredentials | None = None,
    browser_task_publisher: SendCommentTaskPublisher | None = None,
    ids: IdGenerator | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Create the FastAPI application and attach SQLAdmin."""
    app = FastAPI(title="smhelper")
    app_engine = engine if engine is not None else create_engine_from_url(database_url)
    session_factory = create_session_factory(app_engine)
    Base.metadata.create_all(app_engine)
    app.include_router(api_router)
    app.state.candidate_dispatcher = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=ids or UuidGenerator(),
        clock=clock or SystemClock(),
        send_account_policy=SendAccountPolicy(rng=Random()),
        browser_task_publisher=browser_task_publisher
        or _default_browser_task_publisher(),
    )
    configure_admin(
        app=app,
        engine=app_engine,
        credentials=admin_credentials or AdminCredentials.from_env(),
        candidate_dispatcher=app.state.candidate_dispatcher,
    )
    app.state.engine = app_engine
    return app


def _default_browser_task_publisher() -> BrowserTaskPublisher:
    """Create the default Celery browser-task publisher."""
    celery_app = create_celery_app(
        broker_url=getenv("SMHELPER_CELERY_BROKER_URL", "redis://localhost:6379/0"),
        result_backend_url=getenv("SMHELPER_CELERY_RESULT_BACKEND_URL"),
    )
    return BrowserTaskPublisher(celery_app=celery_app)
