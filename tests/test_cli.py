from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import create_engine, inspect

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
    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())
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
    table_names = set(inspect(create_engine(database_url)).get_table_names())
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
    table_names = set(inspect(create_engine(database_url)).get_table_names())
    assert "platform_accounts" in table_names
