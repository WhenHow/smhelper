from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    DispatchJobRecord,
    SendAttemptRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.web.admin import AdminCredentials
from smhelper.web.app import create_app


def test_storage_state_api_serves_valid_account_storage_state(tmp_path: Path) -> None:
    database_path = tmp_path / "smhelper.db"
    storage_state_path = tmp_path / "storage_state.json"
    storage_state_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )
    with Session(engine) as session:
        session.add(
            AccountAuthStateRecord(
                account_id="account-1",
                platform="xhs",
                status="valid",
                storage_state_path=str(storage_state_path),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/api/accounts/xhs/account-1/storage-state")

    assert response.status_code == 200
    assert response.json() == {"cookies": [], "origins": []}
    engine.dispose()


def test_storage_state_api_returns_404_for_expired_auth_state(tmp_path: Path) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )
    with Session(engine) as session:
        session.add(
            AccountAuthStateRecord(
                account_id="account-1",
                platform="xhs",
                status="expired",
                storage_state_path=str(tmp_path / "missing.json"),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/api/accounts/xhs/account-1/storage-state")

    assert response.status_code == 404
    engine.dispose()


def test_session_status_api_updates_worker_reported_session_state(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )
    with Session(engine) as session:
        session.add(
            AccountLiveSessionRecord(
                id="session-1",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="starting",
                active_slot_key="live-1:account-1",
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/api/live/sessions/session-1/status",
            json={"status": "waiting", "failure_reason": None},
        )

    assert response.status_code == 200
    with Session(engine) as session:
        session_record = session.get(AccountLiveSessionRecord, "session-1")
        assert session_record is not None
        assert session_record.status == "waiting"
        assert session_record.active_slot_key == "live-1:account-1"
    engine.dispose()


def test_send_result_api_records_attempt_and_updates_dispatch_job(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
        clock=FixedClock(now),
        send_cooldown_seconds=300,
    )
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
            AccountLiveSessionRecord(
                id="session-1",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-1",
                node_id="node-a",
                status="sending",
                active_slot_key="live-1:account-1",
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
                status="running",
                created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/api/live/send-results",
            json={
                "dispatch_job_id": "job-1",
                "session_id": "session-1",
                "account_id": "account-1",
                "status": "success",
                "failure_reason": None,
            },
        )

    assert response.status_code == 200
    with Session(engine) as session:
        job = session.get(DispatchJobRecord, "job-1")
        session_record = session.get(AccountLiveSessionRecord, "session-1")
        account = session.get(PlatformAccountRecord, "account-1")
        attempts = session.query(SendAttemptRecord).all()
        assert job is not None
        assert job.status == "success"
        assert session_record is not None
        assert session_record.status == "waiting"
        assert session_record.last_send_at == now.replace(tzinfo=None)
        assert session_record.cooldown_until == (now + timedelta(seconds=300)).replace(
            tzinfo=None
        )
        assert account is not None
        assert account.sends_today == 1
        assert account.cooldown_until == (now + timedelta(seconds=300)).replace(
            tzinfo=None
        )
        assert len(attempts) == 1
        assert attempts[0].success_detection == "operation_completed"
        assert attempts[0].attempted_at == now.replace(tzinfo=None)
    engine.dispose()


def test_send_result_api_does_not_increment_send_count_on_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
        clock=FixedClock(now),
        send_cooldown_seconds=300,
    )
    with Session(engine) as session:
        session.add(
            PlatformAccountRecord(
                id="account-1",
                platform="xhs",
                display_name="Account 1",
                enabled=True,
                daily_send_limit=10,
                sends_today=4,
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
                status="sending",
                active_slot_key="live-1:account-1",
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
                status="running",
                created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/api/live/send-results",
            json={
                "dispatch_job_id": "job-1",
                "session_id": "session-1",
                "account_id": "account-1",
                "status": "failed",
                "failure_reason": "input not found",
            },
        )

    assert response.status_code == 200
    with Session(engine) as session:
        job = session.get(DispatchJobRecord, "job-1")
        session_record = session.get(AccountLiveSessionRecord, "session-1")
        account = session.get(PlatformAccountRecord, "account-1")
        assert job is not None
        assert job.status == "failed"
        assert job.failure_reason == "input not found"
        assert session_record is not None
        assert session_record.status == "waiting"
        assert session_record.last_send_at is None
        assert session_record.cooldown_until is None
        assert account is not None
        assert account.sends_today == 4
        assert account.cooldown_until is None
    engine.dispose()
