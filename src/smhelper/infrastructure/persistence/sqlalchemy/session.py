"""SQLAlchemy engine, session factory and unit-of-work helpers."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_from_url(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL."""
    return create_engine(database_url)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory with predictable commit semantics."""
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class SqlAlchemyUnitOfWork:
    """Context manager that commits on success and rolls back on errors."""

    def __init__(self, *, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session

    def __enter__(self) -> Self:
        """Open a SQLAlchemy session."""
        self.session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Commit or roll back the session and then close it."""
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
