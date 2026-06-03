from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import Engine
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.schema import create_database_schema
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper import main


def test_main_exposes_live_assistant_command() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "live-assistant" in result.output


def test_main_exposes_web_command() -> None:
    result = CliRunner().invoke(main, ["web", "--help"])

    assert result.exit_code == 0
    assert "--database-url" in result.output
    assert "--port" in result.output


def test_main_exposes_live_doctor_command() -> None:
    result = CliRunner().invoke(main, ["live", "doctor", "--help"])

    assert result.exit_code == 0
    assert "--database-url" in result.output


def test_main_exposes_db_init_command() -> None:
    result = CliRunner().invoke(main, ["db", "init", "--help"])

    assert result.exit_code == 0
    assert "--database-url" in result.output


def test_db_init_creates_sqlalchemy_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "smhelper.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    result = CliRunner().invoke(main, ["db", "init", "--database-url", database_url])

    assert result.exit_code == 0
    assert "Initialized database schema" in result.output
    table_names = _table_names(database_url)
    assert {
        "account_auth_states",
        "account_live_sessions",
        "candidate_questions",
        "dispatch_jobs",
        "live_segments",
        "live_tasks",
        "platform_accounts",
        "send_attempts",
        "transcripts",
        "worker_nodes",
    } <= table_names


def test_db_init_uses_runtime_database_url_from_env(tmp_path: Path) -> None:
    database_path = tmp_path / "configured.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    result = CliRunner().invoke(
        main,
        ["db", "init"],
        env={"SMHELPER_DATABASE_URL": database_url},
    )

    assert result.exit_code == 0
    table_names = _table_names(database_url)
    assert "live_tasks" in table_names


def test_db_init_explicit_database_url_does_not_read_unrelated_env(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "explicit.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    result = CliRunner().invoke(
        main,
        ["db", "init", "--database-url", database_url],
        env={"SMHELPER_DEFAULT_PLATFORM": ""},
    )

    assert result.exit_code == 0
    table_names = _table_names(database_url)
    assert "platform_accounts" in table_names


def test_live_doctor_fails_when_schema_is_missing(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path / "empty.db")

    result = CliRunner().invoke(
        main,
        ["live", "doctor", "--database-url", database_url],
    )

    assert result.exit_code == 1
    assert "[OK] database connection" in result.output
    assert "[FAIL] database schema" in result.output
    assert "missing table(s):" in result.output


def test_live_doctor_fails_when_required_setup_data_is_missing(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path / "missing-data.db")
    engine = _sqlite_engine(database_url)
    create_database_schema(engine=engine)
    engine.dispose()

    result = CliRunner().invoke(
        main,
        ["live", "doctor", "--database-url", database_url],
    )

    assert result.exit_code == 1
    assert "[OK] database schema" in result.output
    assert "[FAIL] live task setup" in result.output
    assert "[FAIL] account setup" in result.output
    assert "[FAIL] worker setup" in result.output


def test_live_doctor_passes_with_minimum_runtime_setup(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path / "ready.db")
    engine = _sqlite_engine(database_url)
    create_database_schema(engine=engine)
    _seed_minimum_live_runtime(engine)
    engine.dispose()

    result = CliRunner().invoke(
        main,
        ["live", "doctor", "--database-url", database_url],
        env={
            "SMHELPER_ASR_PROVIDER_NAME": "fake-asr",
            "SMHELPER_ASR_PROVIDER_CALLABLE": "tests.fake:provider",
            "SMHELPER_LLM_MODEL": "fake-llm",
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        },
    )

    assert result.exit_code == 0
    assert "[OK] database schema" in result.output
    assert "[OK] live task setup" in result.output
    assert "[OK] account setup" in result.output
    assert "[OK] worker setup" in result.output
    assert "[OK] celery configuration" in result.output
    assert "[OK] asr configuration" in result.output
    assert "[OK] llm configuration" in result.output


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _sqlite_engine(database_url: str) -> Engine:
    return create_engine(database_url, poolclass=NullPool)


def _table_names(database_url: str) -> set[str]:
    engine = _sqlite_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _seed_minimum_live_runtime(engine: Engine) -> None:
    with Session(engine) as session:
        session.add_all(
            [
                LiveTaskRecord(
                    id="live-1",
                    platform="xhs",
                    room_url="https://www.xiaohongshu.com/livestream/1",
                    status="pending",
                    product_context="Product facts",
                    task_context="Ask helpful questions",
                    segment_time_seconds=60,
                    created_at=datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
                ),
                PlatformAccountRecord(
                    id="account-1",
                    platform="xhs",
                    display_name="Account 1",
                    enabled=True,
                    daily_send_limit=20,
                    sends_today=0,
                ),
                AccountAuthStateRecord(
                    account_id="account-1",
                    platform="xhs",
                    status="valid",
                    storage_state_path="data/auth/account-1/storage_state.json",
                ),
                WorkerNodeRecord(
                    id="node-1",
                    queue_name="node.node-1.browser",
                    supported_platforms=["xhs"],
                    max_browser_sessions=1,
                    active_browser_sessions=0,
                    online=True,
                ),
            ]
        )
        session.commit()
