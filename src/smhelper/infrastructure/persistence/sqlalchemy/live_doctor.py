"""Read-only runtime checks for the first-phase live assistant setup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Literal, Mapping

from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import LiveTaskRecord
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord

DoctorStatus = Literal["ok", "warn", "fail"]
_STARTABLE_LIVE_TASK_STATUSES = frozenset({"pending", "created", "ready", "running"})


@dataclass(frozen=True, slots=True)
class LiveDoctorCheck:
    """One doctor check result."""

    status: DoctorStatus
    name: str
    message: str

    def render(self) -> str:
        """Render a stable CLI line."""
        return f"[{self.status.upper()}] {self.name}: {self.message}"


@dataclass(frozen=True, slots=True)
class LiveDoctorReport:
    """Aggregated live doctor report."""

    checks: tuple[LiveDoctorCheck, ...]

    @property
    def has_failures(self) -> bool:
        """Return whether any required check failed."""
        return any(check.status == "fail" for check in self.checks)

    def render(self) -> str:
        """Render all checks for CLI output."""
        return "\n".join(check.render() for check in self.checks)


def run_live_doctor(
    *,
    database_url: str | None = None,
    settings: RuntimeSettings | None = None,
    engine: Engine | None = None,
    env: Mapping[str, str] | None = None,
) -> LiveDoctorReport:
    """Run read-only setup checks for the live assistant runtime."""
    resolved_settings = settings or RuntimeSettings.from_env()
    checks: list[LiveDoctorCheck] = []
    own_engine = engine is None
    resolved_engine = engine or create_engine_from_url(
        database_url or resolved_settings.database_url
    )
    try:
        try:
            with resolved_engine.connect() as connection:
                existing_tables = set(inspect(connection).get_table_names())
            checks.append(
                LiveDoctorCheck(
                    status="ok",
                    name="database connection",
                    message="connected",
                )
            )
        except SQLAlchemyError as exc:
            checks.append(
                LiveDoctorCheck(
                    status="fail",
                    name="database connection",
                    message=str(exc),
                )
            )
            checks.extend(_configuration_checks(resolved_settings, env=env))
            return LiveDoctorReport(tuple(checks))

        expected_tables = set(Base.metadata.tables)
        missing_tables = sorted(expected_tables - existing_tables)
        if missing_tables:
            checks.append(
                LiveDoctorCheck(
                    status="fail",
                    name="database schema",
                    message=f"missing table(s): {', '.join(missing_tables)}",
                )
            )
            checks.extend(_configuration_checks(resolved_settings, env=env))
            return LiveDoctorReport(tuple(checks))
        checks.append(
            LiveDoctorCheck(
                status="ok",
                name="database schema",
                message=f"{len(expected_tables)} required table(s) present",
            )
        )

        with Session(resolved_engine) as session:
            checks.extend(
                _data_checks(session, platform=resolved_settings.default_platform)
            )
        checks.extend(_configuration_checks(resolved_settings, env=env))
        return LiveDoctorReport(tuple(checks))
    finally:
        if own_engine:
            resolved_engine.dispose()


def _data_checks(session: Session, *, platform: str) -> tuple[LiveDoctorCheck, ...]:
    live_tasks = session.scalars(
        select(LiveTaskRecord).where(
            LiveTaskRecord.platform == platform,
            LiveTaskRecord.status.in_(_STARTABLE_LIVE_TASK_STATUSES),
        )
    ).all()
    enabled_accounts = session.scalars(
        select(PlatformAccountRecord).where(
            PlatformAccountRecord.platform == platform,
            PlatformAccountRecord.enabled.is_(True),
        )
    ).all()
    valid_auth_account_ids = set(
        session.scalars(
            select(AccountAuthStateRecord.account_id).where(
                AccountAuthStateRecord.platform == platform,
                AccountAuthStateRecord.status == "valid",
            )
        ).all()
    )
    ready_account_count = sum(
        1 for account in enabled_accounts if account.id in valid_auth_account_ids
    )
    workers = session.scalars(
        select(WorkerNodeRecord).where(WorkerNodeRecord.online.is_(True))
    ).all()
    ready_worker_count = sum(
        1 for worker in workers if platform in (worker.supported_platforms or [])
    )
    return (
        _required_count_check(
            name="live task setup",
            count=len(live_tasks),
            ok_message=f"{len(live_tasks)} startable live task(s) for {platform}",
            fail_message=(
                f"no {platform} live task with status pending, created, ready or running"
            ),
        ),
        _required_count_check(
            name="account setup",
            count=ready_account_count,
            ok_message=f"{ready_account_count} enabled account(s) with valid auth state",
            fail_message=f"no enabled {platform} account with valid auth state",
        ),
        _required_count_check(
            name="worker setup",
            count=ready_worker_count,
            ok_message=f"{ready_worker_count} online worker node(s) support {platform}",
            fail_message=f"no online worker node supports {platform}",
        ),
    )


def _configuration_checks(
    settings: RuntimeSettings,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[LiveDoctorCheck, ...]:
    source_env = os.environ if env is None else env
    checks = [
        LiveDoctorCheck(
            status="ok",
            name="celery configuration",
            message=(
                f"broker={settings.celery_broker_url} "
                f"result_backend={settings.celery_result_backend_url}"
            ),
        )
    ]
    checks.append(_ffmpeg_check(settings.ffmpeg_path))
    checks.append(_asr_check(settings))
    checks.append(_llm_check(settings, env=source_env))
    return tuple(checks)


def _ffmpeg_check(ffmpeg_path: str) -> LiveDoctorCheck:
    resolved_path = Path(ffmpeg_path)
    if resolved_path.exists() or which(ffmpeg_path) is not None:
        return LiveDoctorCheck(
            status="ok",
            name="ffmpeg configuration",
            message=f"{ffmpeg_path} is available",
        )
    return LiveDoctorCheck(
        status="warn",
        name="ffmpeg configuration",
        message=f"{ffmpeg_path} was not found on PATH",
    )


def _asr_check(settings: RuntimeSettings) -> LiveDoctorCheck:
    if settings.asr_provider_name and settings.asr_provider_callable:
        return LiveDoctorCheck(
            status="ok",
            name="asr configuration",
            message=f"provider={settings.asr_provider_name}",
        )
    return LiveDoctorCheck(
        status="warn",
        name="asr configuration",
        message="SMHELPER_ASR_PROVIDER_NAME and SMHELPER_ASR_PROVIDER_CALLABLE not set",
    )


def _llm_check(
    settings: RuntimeSettings,
    *,
    env: Mapping[str, str],
) -> LiveDoctorCheck:
    local_cost_map_enabled = env.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"
    if settings.llm_model and local_cost_map_enabled:
        return LiveDoctorCheck(
            status="ok",
            name="llm configuration",
            message=f"model={settings.llm_model}",
        )
    missing: list[str] = []
    if settings.llm_model is None:
        missing.append("SMHELPER_LLM_MODEL")
    if not local_cost_map_enabled:
        missing.append("LITELLM_LOCAL_MODEL_COST_MAP=True")
    return LiveDoctorCheck(
        status="warn",
        name="llm configuration",
        message=f"missing {', '.join(missing)}",
    )


def _required_count_check(
    *,
    name: str,
    count: int,
    ok_message: str,
    fail_message: str,
) -> LiveDoctorCheck:
    if count > 0:
        return LiveDoctorCheck(status="ok", name=name, message=ok_message)
    return LiveDoctorCheck(status="fail", name=name, message=fail_message)
