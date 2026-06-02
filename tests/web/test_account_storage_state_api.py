from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    DispatchJobRecord,
    LiveTaskRecord,
    SendAttemptRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import EnterLiveRoomPayload
from smhelper.web.admin import AdminCredentials
from smhelper.web.app import create_app


class FakeBrowserTaskPublisher:
    def __init__(self) -> None:
        self.entered: list[tuple[str, EnterLiveRoomPayload, int]] = []

    def enter_live_room(
        self,
        *,
        queue_name: str,
        payload: EnterLiveRoomPayload,
        countdown_seconds: int,
    ) -> None:
        self.entered.append((queue_name, payload, countdown_seconds))

    def send_comment(
        self,
        *,
        queue_name: str,
        payload: object,
    ) -> None:
        raise AssertionError(f"unexpected send_comment call on {queue_name}: {payload}")


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


def test_session_status_api_ignores_stale_active_report_for_terminal_session(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    closed_at = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    report_at = datetime(2026, 6, 2, 10, 5, tzinfo=UTC)
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
        clock=FixedClock(report_at),
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
                status="closed",
                active_slot_key=None,
                closed_at=closed_at,
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/api/live/sessions/session-1/status",
            json={"status": "waiting", "failure_reason": None},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    with Session(engine) as session:
        session_record = session.get(AccountLiveSessionRecord, "session-1")
        assert session_record is not None
        assert session_record.status == "closed"
        assert session_record.active_slot_key is None
        assert session_record.closed_at == closed_at.replace(tzinfo=None)
        assert session_record.last_heartbeat_at is None
    engine.dispose()


def test_session_status_api_restarts_failed_session_when_live_task_is_running(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
        browser_task_publisher=publisher,
        clock=FixedClock(now),
        ids=SequenceIdGenerator(["session-restart"]),
    )
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="running",
                segment_time_seconds=60,
                created_at=now,
                started_at=now,
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
            json={"status": "failed", "failure_reason": "browser_crashed"},
        )

    assert response.status_code == 200
    assert len(publisher.entered) == 1
    queue_name, payload, countdown_seconds = publisher.entered[0]
    assert queue_name == "node.node-a.browser"
    assert payload.account_id == "account-1"
    assert payload.live_task_id == "live-1"
    assert payload.room_url == "https://example.com/live/1"
    assert payload.platform == "xhs"
    assert countdown_seconds == 0
    assert payload.session_id == "session-restart"
    with Session(engine) as session:
        failed_session = session.get(AccountLiveSessionRecord, "session-1")
        restarted_session = session.get(AccountLiveSessionRecord, payload.session_id)
        assert failed_session is not None
        assert failed_session.status == "failed"
        assert failed_session.failure_reason == "browser_crashed"
        assert failed_session.active_slot_key is None
        assert failed_session.closed_at == now.replace(tzinfo=None)
        assert restarted_session is not None
        assert restarted_session.status == "planned"
        assert restarted_session.account_id == "account-1"
        assert restarted_session.node_id == "node-a"
        assert restarted_session.restart_count == 1
        assert restarted_session.active_slot_key == "live-1:account-1"
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


def test_send_result_api_ignores_duplicate_terminal_result(
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
        first_response = client.post(
            "/api/live/send-results",
            json={
                "dispatch_job_id": "job-1",
                "session_id": "session-1",
                "account_id": "account-1",
                "status": "success",
                "failure_reason": None,
            },
        )
        second_response = client.post(
            "/api/live/send-results",
            json={
                "dispatch_job_id": "job-1",
                "session_id": "session-1",
                "account_id": "account-1",
                "status": "success",
                "failure_reason": None,
            },
        )

    assert first_response.status_code == 200
    assert first_response.json() == {"status": "ok"}
    assert second_response.status_code == 200
    assert second_response.json() == {"status": "ignored"}
    with Session(engine) as session:
        job = session.get(DispatchJobRecord, "job-1")
        account = session.get(PlatformAccountRecord, "account-1")
        attempts = session.query(SendAttemptRecord).all()
        assert job is not None
        assert job.status == "success"
        assert account is not None
        assert account.sends_today == 1
        assert len(attempts) == 1
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


def test_send_result_api_rejects_mismatched_job_session_and_account(
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
            PlatformAccountRecord(
                id="account-2",
                platform="xhs",
                display_name="Account 2",
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
            AccountLiveSessionRecord(
                id="session-2",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-2",
                node_id="node-a",
                status="waiting",
                active_slot_key="live-1:account-2",
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
                "session_id": "session-2",
                "account_id": "account-2",
                "status": "success",
                "failure_reason": None,
            },
        )

    assert response.status_code == 409
    with Session(engine) as session:
        job = session.get(DispatchJobRecord, "job-1")
        original_session = session.get(AccountLiveSessionRecord, "session-1")
        mismatched_session = session.get(AccountLiveSessionRecord, "session-2")
        original_account = session.get(PlatformAccountRecord, "account-1")
        mismatched_account = session.get(PlatformAccountRecord, "account-2")
        attempts = session.query(SendAttemptRecord).all()
        assert job is not None
        assert job.status == "running"
        assert job.finished_at is None
        assert original_session is not None
        assert original_session.status == "sending"
        assert mismatched_session is not None
        assert mismatched_session.status == "waiting"
        assert original_account is not None
        assert original_account.sends_today == 0
        assert mismatched_account is not None
        assert mismatched_account.sends_today == 0
        assert attempts == []
    engine.dispose()
