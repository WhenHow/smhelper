"""Development data setup for local live-assistant testing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from smhelper.core.config import RuntimeSettings
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    CandidateQuestionRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.schema import create_database_schema
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord


@dataclass(frozen=True, slots=True)
class LiveDevSeedResult:
    """Summary of records written by the development seed command."""

    live_task_id: str
    account_id: str
    node_id: str
    queue_name: str
    review_demo_candidate_id: str | None = None
    review_demo_session_id: str | None = None


def seed_live_dev_setup(
    *,
    room_url: str,
    storage_state_path: str,
    database_url: str | None = None,
    live_task_id: str = "live-1",
    account_id: str = "account-1",
    node_id: str = "node-1",
    max_browser_sessions: int = 1,
    with_review_demo: bool = False,
    engine: Engine | None = None,
) -> LiveDevSeedResult:
    """Create or update the minimum records needed to test the live flow locally."""
    settings = RuntimeSettings.from_env()
    resolved_engine = engine or create_engine_from_url(
        database_url or settings.database_url
    )
    own_engine = engine is None
    try:
        create_database_schema(engine=resolved_engine)
        with Session(resolved_engine) as session:
            queue_name = f"node.{node_id}.browser"
            _upsert_live_task(
                session,
                live_task_id=live_task_id,
                platform=settings.default_platform,
                room_url=room_url,
            )
            _upsert_account(
                session,
                account_id=account_id,
                platform=settings.default_platform,
            )
            _upsert_auth_state(
                session,
                account_id=account_id,
                platform=settings.default_platform,
                storage_state_path=storage_state_path,
            )
            _upsert_worker(
                session,
                node_id=node_id,
                platform=settings.default_platform,
                queue_name=queue_name,
                max_browser_sessions=max_browser_sessions,
            )
            review_demo_candidate_id: str | None = None
            review_demo_session_id: str | None = None
            if with_review_demo:
                _mark_live_task_running_for_review_demo(
                    session,
                    live_task_id=live_task_id,
                    stream_url="dev-review-demo-stream",
                )
                review_demo_session_id = _upsert_review_demo_session(
                    session,
                    live_task_id=live_task_id,
                    platform=settings.default_platform,
                    room_url=room_url,
                    account_id=account_id,
                    node_id=node_id,
                )
                review_demo_candidate_id = _upsert_review_demo_candidate(
                    session,
                    live_task_id=live_task_id,
                )
            session.commit()
        return LiveDevSeedResult(
            live_task_id=live_task_id,
            account_id=account_id,
            node_id=node_id,
            queue_name=queue_name,
            review_demo_candidate_id=review_demo_candidate_id,
            review_demo_session_id=review_demo_session_id,
        )
    finally:
        if own_engine:
            resolved_engine.dispose()


def _upsert_live_task(
    session: Session,
    *,
    live_task_id: str,
    platform: str,
    room_url: str,
) -> None:
    live_task = session.get(LiveTaskRecord, live_task_id)
    if live_task is None:
        session.add(
            LiveTaskRecord(
                id=live_task_id,
                platform=platform,
                room_url=room_url,
                status="pending",
                product_context="",
                task_context="",
                segment_time_seconds=60,
                created_at=datetime.now(UTC),
            )
        )
        return
    live_task.platform = platform
    live_task.room_url = room_url
    live_task.status = "pending"
    live_task.product_context = live_task.product_context or ""
    live_task.task_context = live_task.task_context or ""
    live_task.segment_time_seconds = live_task.segment_time_seconds or 60
    live_task.created_at = live_task.created_at or datetime.now(UTC)


def _upsert_account(
    session: Session,
    *,
    account_id: str,
    platform: str,
) -> None:
    account = session.get(PlatformAccountRecord, account_id)
    if account is None:
        session.add(
            PlatformAccountRecord(
                id=account_id,
                platform=platform,
                display_name=account_id,
                enabled=True,
                daily_send_limit=20,
                sends_today=0,
            )
        )
        return
    account.platform = platform
    account.enabled = True
    account.daily_send_limit = account.daily_send_limit or 20
    account.sends_today = 0


def _upsert_auth_state(
    session: Session,
    *,
    account_id: str,
    platform: str,
    storage_state_path: str,
) -> None:
    auth_state = session.get(AccountAuthStateRecord, (account_id, platform))
    now = datetime.now(UTC)
    if auth_state is None:
        session.add(
            AccountAuthStateRecord(
                account_id=account_id,
                platform=platform,
                status="valid",
                storage_state_path=storage_state_path,
                updated_at=now,
            )
        )
        return
    auth_state.status = "valid"
    auth_state.storage_state_path = storage_state_path
    auth_state.failure_reason = None
    auth_state.updated_at = now


def _upsert_worker(
    session: Session,
    *,
    node_id: str,
    platform: str,
    queue_name: str,
    max_browser_sessions: int,
) -> None:
    worker = session.get(WorkerNodeRecord, node_id)
    if worker is None:
        session.add(
            WorkerNodeRecord(
                id=node_id,
                queue_name=queue_name,
                supported_platforms=[platform],
                max_browser_sessions=max_browser_sessions,
                active_browser_sessions=0,
                online=True,
            )
        )
        return
    worker.queue_name = queue_name
    worker.supported_platforms = [platform]
    worker.max_browser_sessions = max_browser_sessions
    worker.active_browser_sessions = 0
    worker.online = True


def _mark_live_task_running_for_review_demo(
    session: Session,
    *,
    live_task_id: str,
    stream_url: str,
) -> None:
    live_task = session.get(LiveTaskRecord, live_task_id)
    if live_task is None:
        return
    live_task.status = "running"
    live_task.stream_url = stream_url
    live_task.started_at = live_task.started_at or datetime.now(UTC)


def _upsert_review_demo_session(
    session: Session,
    *,
    live_task_id: str,
    platform: str,
    room_url: str,
    account_id: str,
    node_id: str,
) -> str | None:
    session_id = "session-demo-1"
    active_slot_key = AccountLiveSessionRecord.build_active_slot_key(
        live_task_id=live_task_id,
        account_id=account_id,
        status="waiting",
    )
    existing_active_session = session.scalars(
        select(AccountLiveSessionRecord).where(
            AccountLiveSessionRecord.active_slot_key == active_slot_key
        )
    ).first()
    if existing_active_session is not None and existing_active_session.id != session_id:
        return None

    live_session = session.get(AccountLiveSessionRecord, session_id)
    if live_session is None:
        session.add(
            AccountLiveSessionRecord(
                id=session_id,
                live_task_id=live_task_id,
                platform=platform,
                room_url=room_url,
                account_id=account_id,
                node_id=node_id,
                status="waiting",
                active_slot_key=active_slot_key,
                opened_at=datetime.now(UTC),
                restart_count=0,
            )
        )
        return session_id

    live_session.live_task_id = live_task_id
    live_session.platform = platform
    live_session.room_url = room_url
    live_session.account_id = account_id
    live_session.node_id = node_id
    live_session.status = "waiting"
    live_session.active_slot_key = active_slot_key
    live_session.failure_reason = None
    live_session.closed_at = None
    live_session.send_started_at = None
    return session_id


def _upsert_review_demo_candidate(
    session: Session,
    *,
    live_task_id: str,
) -> str:
    candidate_id = "candidate-demo-1"
    candidate = session.get(CandidateQuestionRecord, candidate_id)
    if candidate is None:
        session.add(
            CandidateQuestionRecord(
                id=candidate_id,
                live_task_id=live_task_id,
                segment_id="segment-demo-1",
                question="Is this product suitable for oily skin?",
                reason="Development review demo candidate.",
                risk_level="low",
                raw_response=(
                    '{"question":"Is this product suitable for oily skin?",'
                    '"reason":"Development review demo candidate.",'
                    '"risk_level":"low"}'
                ),
                status="pending_review",
                generated_at=datetime.now(UTC),
                final_text="Is this product suitable for oily skin?",
            )
        )
        return candidate_id

    candidate.live_task_id = live_task_id
    candidate.segment_id = "segment-demo-1"
    candidate.question = "Is this product suitable for oily skin?"
    candidate.reason = "Development review demo candidate."
    candidate.risk_level = "low"
    candidate.raw_response = (
        '{"question":"Is this product suitable for oily skin?",'
        '"reason":"Development review demo candidate.",'
        '"risk_level":"low"}'
    )
    candidate.status = "pending_review"
    candidate.final_text = "Is this product suitable for oily skin?"
    candidate.reviewed_by = None
    candidate.reviewed_at = None
    candidate.rejection_reason = None
    return candidate_id
