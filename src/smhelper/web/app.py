"""FastAPI application factory for smhelper management backend."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import Engine

from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.web.api import router as api_router
from smhelper.web.admin import AdminCredentials, configure_admin


def create_app(
    *,
    database_url: str = "sqlite+pysqlite:///data/smhelper.db",
    engine: Engine | None = None,
    admin_credentials: AdminCredentials | None = None,
) -> FastAPI:
    """Create the FastAPI application and attach SQLAdmin."""
    app = FastAPI(title="smhelper")
    app_engine = engine if engine is not None else create_engine_from_url(database_url)
    Base.metadata.create_all(app_engine)
    app.include_router(api_router)
    configure_admin(
        app=app,
        engine=app_engine,
        credentials=admin_credentials or AdminCredentials.from_env(),
    )
    app.state.engine = app_engine
    return app
