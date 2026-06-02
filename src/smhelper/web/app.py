"""FastAPI application factory for smhelper management backend."""

from __future__ import annotations

from random import Random
from typing import Protocol

from fastapi import FastAPI
from sqlalchemy import Engine

from smhelper.core.clock import Clock, SystemClock
from smhelper.core.config import RuntimeSettings
from smhelper.core.ids import IdGenerator, UuidGenerator
from smhelper.infrastructure.persistence.sqlalchemy.account_entry_dispatcher import (
    EnterLiveRoomTaskPublisher,
    SqlAlchemyAccountEntryDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.account_session_restarter import (
    SqlAlchemyAccountSessionRestarter,
)
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.candidate_dispatcher import (
    SendCommentTaskPublisher,
    SqlAlchemyCandidateDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.candidate_reviewer import (
    SqlAlchemyCandidateReviewer,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.task_queue.celery.app import create_celery_app
from smhelper.infrastructure.task_queue.celery.publisher import (
    BrowserTaskPublisher as CeleryBrowserTaskPublisher,
)
from smhelper.live.domain.policies.send_account_policy import SendAccountPolicy
from smhelper.web.api import router as api_router
from smhelper.web.admin import AdminCredentials, configure_admin


class BrowserTaskPublisherProtocol(
    SendCommentTaskPublisher,
    EnterLiveRoomTaskPublisher,
    Protocol,
):
    """Publisher surface needed by center-side browser task orchestration."""


def create_app(
    *,
    database_url: str | None = None,
    engine: Engine | None = None,
    admin_credentials: AdminCredentials | None = None,
    browser_task_publisher: BrowserTaskPublisherProtocol | None = None,
    ids: IdGenerator | None = None,
    clock: Clock | None = None,
    send_cooldown_seconds: int | None = None,
) -> FastAPI:
    """Create the FastAPI application and attach SQLAdmin."""
    app = FastAPI(title="smhelper")
    settings = RuntimeSettings.from_env()
    resolved_database_url = database_url or settings.database_url
    app_engine = (
        engine if engine is not None else create_engine_from_url(resolved_database_url)
    )
    session_factory = create_session_factory(app_engine)
    Base.metadata.create_all(app_engine)
    app.include_router(api_router)
    resolved_clock = clock or SystemClock()
    resolved_ids = ids or UuidGenerator()
    resolved_browser_task_publisher = browser_task_publisher or (
        _default_browser_task_publisher(settings)
    )
    app.state.clock = resolved_clock
    app.state.send_cooldown_seconds = (
        settings.send_cooldown_seconds
        if send_cooldown_seconds is None
        else send_cooldown_seconds
    )
    app.state.candidate_dispatcher = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=resolved_ids,
        clock=resolved_clock,
        send_account_policy=SendAccountPolicy(rng=Random()),
        browser_task_publisher=resolved_browser_task_publisher,
    )
    app.state.candidate_reviewer = SqlAlchemyCandidateReviewer(
        session_factory=session_factory,
        clock=resolved_clock,
    )
    app.state.account_session_restarter = SqlAlchemyAccountSessionRestarter(
        session_factory=session_factory,
        ids=resolved_ids,
        dispatcher=SqlAlchemyAccountEntryDispatcher(
            session_factory=session_factory,
            browser_task_publisher=resolved_browser_task_publisher,
        ),
    )
    configure_admin(
        app=app,
        engine=app_engine,
        credentials=admin_credentials or AdminCredentials.from_env(),
        candidate_dispatcher=app.state.candidate_dispatcher,
        candidate_reviewer=app.state.candidate_reviewer,
    )
    app.state.engine = app_engine
    return app


def _default_browser_task_publisher(
    settings: RuntimeSettings,
) -> CeleryBrowserTaskPublisher:
    """Create the default Celery browser-task publisher."""
    celery_app = create_celery_app(
        broker_url=settings.celery_broker_url,
        result_backend_url=settings.celery_result_backend_url,
    )
    return CeleryBrowserTaskPublisher(celery_app=celery_app)
