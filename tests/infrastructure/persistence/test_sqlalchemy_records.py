from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    CandidateQuestionRecord,
    DispatchJobRecord,
    LiveTaskRecord,
    SendAttemptRecord,
    TranscriptRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord


def test_sqlalchemy_metadata_contains_core_live_assistant_tables() -> None:
    expected_tables = {
        "platform_accounts",
        "account_auth_states",
        "worker_nodes",
        "live_tasks",
        "candidate_questions",
        "account_live_sessions",
        "dispatch_jobs",
        "send_attempts",
        "live_segments",
        "transcripts",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_sqlalchemy_records_can_be_persisted_together() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    with Session(engine) as session:
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
        session.add(
            AccountAuthStateRecord(
                account_id="account-1",
                platform="xhs",
                status="valid",
                storage_state_path="data/auth/xhs/account-1/storage_state.json",
            )
        )
        session.add(
            WorkerNodeRecord(
                id="node-a",
                queue_name="node.node-a.browser",
                supported_platforms=["xhs"],
                max_browser_sessions=10,
                active_browser_sessions=1,
                online=True,
            )
        )
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="running",
                product_context="Product facts.",
                task_context="Ask product questions.",
                segment_time_seconds=60,
                created_at=now,
            )
        )
        session.add(
            CandidateQuestionRecord(
                id="candidate-1",
                live_task_id="live-1",
                segment_id="segment-1",
                question="Does this work for oily skin?",
                reason="The segment mentions skin type.",
                risk_level="low",
                raw_response="{}",
                status="pending_review",
                generated_at=now,
            )
        )
        session.add(
            TranscriptRecord(
                id="transcript-1",
                live_task_id="live-1",
                segment_id="segment-1",
                provider_name="vendor-a",
                text="The host is talking about skin type.",
                raw_response='{"ok":true}',
                status="success",
                transcribed_at=now,
            )
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-1",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="waiting",
                active_slot_key=AccountLiveSessionRecord.build_active_slot_key(
                    live_task_id="live-1",
                    account_id="account-1",
                    status="waiting",
                ),
            )
        )
        session.add(
            DispatchJobRecord(
                id="job-1",
                candidate_question_id="candidate-1",
                live_task_id="live-1",
                account_live_session_id="session-1",
                account_id="account-1",
                final_text="Is this suitable for oily skin?",
                status="pending",
                created_at=now,
            )
        )
        session.add(
            SendAttemptRecord(
                id="attempt-1",
                dispatch_job_id="job-1",
                account_live_session_id="session-1",
                account_id="account-1",
                status="success",
                success_detection="operation_completed",
                attempted_at=now,
            )
        )
        session.commit()

    with Session(engine) as session:
        account = session.get(PlatformAccountRecord, "account-1")
        session_record = session.get(AccountLiveSessionRecord, "session-1")

        assert account is not None
        assert account.display_name == "Account 1"
        live_task = session.get(LiveTaskRecord, "live-1")
        assert live_task is not None
        assert live_task.product_context == "Product facts."
        assert live_task.task_context == "Ask product questions."
        assert session_record is not None
        assert session_record.active_slot_key == "live-1:account-1"
    engine.dispose()


def test_account_live_session_active_slot_key_prevents_duplicate_active_sessions() -> (
    None
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                AccountLiveSessionRecord(
                    id="session-1",
                    live_task_id="live-1",
                    platform="xhs",
                    room_url="https://example.com/live/1",
                    account_id="account-1",
                    node_id="node-a",
                    status="waiting",
                    active_slot_key=AccountLiveSessionRecord.build_active_slot_key(
                        live_task_id="live-1",
                        account_id="account-1",
                        status="waiting",
                    ),
                ),
                AccountLiveSessionRecord(
                    id="session-2",
                    live_task_id="live-1",
                    platform="xhs",
                    room_url="https://example.com/live/1",
                    account_id="account-1",
                    node_id="node-a",
                    status="starting",
                    active_slot_key=AccountLiveSessionRecord.build_active_slot_key(
                        live_task_id="live-1",
                        account_id="account-1",
                        status="starting",
                    ),
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_account_live_session_terminal_records_do_not_occupy_active_slot() -> None:
    assert (
        AccountLiveSessionRecord.build_active_slot_key(
            live_task_id="live-1",
            account_id="account-1",
            status="closed",
        )
        is None
    )
