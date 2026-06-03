from __future__ import annotations

import pytest
from sqlalchemy import select

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    PlatformAccountRecord,
)
import smhelper.infrastructure.persistence.sqlalchemy.schema as schema_module
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    SqlAlchemyUnitOfWork,
    create_engine_from_url,
    create_session_factory,
)


def test_session_factory_creates_sessions_for_configured_database_url() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)

    with session_factory() as session:
        session.add(
            PlatformAccountRecord(
                id="account-1",
                platform="xhs",
                display_name="Account 1",
                enabled=True,
                daily_send_limit=10,
                sends_today=0,
            )
        )
        session.commit()

    with session_factory() as session:
        account = session.scalar(
            select(PlatformAccountRecord).where(PlatformAccountRecord.id == "account-1")
        )

    assert account is not None
    assert account.display_name == "Account 1"
    engine.dispose()


def test_create_database_schema_disposes_engine_it_creates(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine_from_url(f"sqlite+pysqlite:///{tmp_path / 'schema.db'}")
    original_dispose = engine.dispose
    disposed = False

    def track_dispose() -> None:
        nonlocal disposed
        disposed = True
        original_dispose()

    monkeypatch.setattr(schema_module, "create_engine_from_url", lambda _: engine)
    monkeypatch.setattr(engine, "dispose", track_dispose)

    try:
        table_names = schema_module.create_database_schema(database_url="ignored")
    finally:
        if not disposed:
            original_dispose()

    assert "platform_accounts" in table_names
    assert disposed is True


def test_create_database_schema_keeps_caller_owned_engine_open(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine_from_url(
        f"sqlite+pysqlite:///{tmp_path / 'caller-owned.db'}"
    )
    original_dispose = engine.dispose
    disposed = False

    def track_dispose() -> None:
        nonlocal disposed
        disposed = True
        original_dispose()

    monkeypatch.setattr(engine, "dispose", track_dispose)

    try:
        table_names = schema_module.create_database_schema(engine=engine)
        assert "platform_accounts" in table_names
        assert disposed is False
    finally:
        original_dispose()


def test_unit_of_work_commits_on_success() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)

    with SqlAlchemyUnitOfWork(session_factory=session_factory) as uow:
        uow.session.add(
            PlatformAccountRecord(
                id="account-1",
                platform="xhs",
                display_name="Account 1",
                enabled=True,
                daily_send_limit=10,
                sends_today=0,
            )
        )

    with session_factory() as session:
        assert session.get(PlatformAccountRecord, "account-1") is not None
    engine.dispose()


def test_unit_of_work_rolls_back_on_error() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)

    with pytest.raises(RuntimeError, match="boom"):
        with SqlAlchemyUnitOfWork(session_factory=session_factory) as uow:
            uow.session.add(
                PlatformAccountRecord(
                    id="account-1",
                    platform="xhs",
                    display_name="Account 1",
                    enabled=True,
                    daily_send_limit=10,
                    sends_today=0,
                )
            )
            raise RuntimeError("boom")

    with session_factory() as session:
        assert session.get(PlatformAccountRecord, "account-1") is None
    engine.dispose()
