"""Database schema initialization helpers."""

from __future__ import annotations

from sqlalchemy import Engine

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.persistence.sqlalchemy import accounts, live, workers
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)

_MAPPED_MODULES = (accounts, live, workers)


def create_database_schema(
    *,
    database_url: str | None = None,
    engine: Engine | None = None,
) -> tuple[str, ...]:
    """Create all ORM tables and return the known table names.

    Importing the mapped modules here keeps schema initialization explicit. A
    caller should not need to know which persistence modules must be imported
    before SQLAlchemy has a complete metadata registry.
    """
    owns_engine = engine is None
    if engine is None:
        resolved_database_url = database_url
        if resolved_database_url is None:
            resolved_database_url = RuntimeSettings.from_env().database_url
        resolved_engine = create_engine_from_url(resolved_database_url)
    else:
        resolved_engine = engine
    try:
        Base.metadata.create_all(resolved_engine)
        return tuple(sorted(Base.metadata.tables))
    finally:
        if owns_engine:
            resolved_engine.dispose()
