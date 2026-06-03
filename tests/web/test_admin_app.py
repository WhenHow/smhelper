from __future__ import annotations

from asyncio import run

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.web.admin import AdminCredentials, SingleAdminAuth
from smhelper.web.admin_views.accounts import AccountAuthStateAdmin
from smhelper.web.admin_views.candidates import CandidateQuestionAdmin
from smhelper.web.admin_views.dispatch_jobs import DispatchJobAdmin, SendAttemptAdmin
from smhelper.web.admin_views.live_tasks import LiveTaskAdmin
from smhelper.web.admin_views.segments import LiveSegmentAdmin, TranscriptAdmin
from smhelper.web.app import create_app
import smhelper.web.app as web_app


def test_create_app_registers_sqladmin_route_and_model_views() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")

    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )

    assert "/admin" in {route.path for route in app.routes}
    assert [view.__class__.__name__ for view in app.state.admin.views] == [
        "PlatformAccountAdmin",
        "AccountAuthStateAdmin",
        "WorkerNodeAdmin",
        "LiveTaskAdmin",
        "LiveSegmentAdmin",
        "TranscriptAdmin",
        "CandidateQuestionAdmin",
        "AccountLiveSessionAdmin",
        "DispatchJobAdmin",
        "SendAttemptAdmin",
    ]
    engine.dispose()


def test_account_auth_state_admin_shows_metadata_without_raw_storage_state() -> None:
    assert AccountAuthStateAdmin.column_list == [
        "account_id",
        "platform",
        "status",
        "storage_state_path",
        "failure_reason",
        "updated_at",
    ]


def test_candidate_question_admin_shows_review_context_and_outcome() -> None:
    assert CandidateQuestionAdmin.column_list == [
        "id",
        "live_task_id",
        "segment_id",
        "question",
        "reason",
        "risk_level",
        "status",
        "final_text",
        "reviewed_by",
        "reviewed_at",
        "rejection_reason",
    ]


def test_dispatch_job_admin_shows_final_text_and_send_status() -> None:
    assert DispatchJobAdmin.column_list == [
        "id",
        "candidate_question_id",
        "live_task_id",
        "account_live_session_id",
        "account_id",
        "final_text",
        "status",
        "created_at",
        "started_at",
        "finished_at",
        "failure_reason",
    ]


def test_send_attempt_admin_shows_page_snapshot_for_failed_send_audit() -> None:
    assert SendAttemptAdmin.column_list == [
        "id",
        "dispatch_job_id",
        "account_live_session_id",
        "account_id",
        "status",
        "success_detection",
        "attempted_at",
        "failure_reason",
        "page_snapshot_path",
    ]


def test_live_task_admin_shows_task_title_and_runtime_status() -> None:
    assert LiveTaskAdmin.column_list == [
        "id",
        "title",
        "platform",
        "room_url",
        "status",
        "stream_url",
        "product_context",
        "task_context",
        "segment_time_seconds",
        "created_at",
        "started_at",
        "ended_at",
        "failure_reason",
    ]


def test_live_segment_admin_shows_media_artifact_paths() -> None:
    assert LiveSegmentAdmin.column_list == [
        "id",
        "live_task_id",
        "sequence",
        "video_path",
        "first_frame_path",
        "last_frame_path",
        "audio_path",
        "completed",
        "created_at",
        "completed_at",
    ]


def test_transcript_admin_shows_asr_result_and_failure_state() -> None:
    assert TranscriptAdmin.column_list == [
        "id",
        "live_task_id",
        "segment_id",
        "provider_name",
        "text",
        "raw_response",
        "status",
        "transcribed_at",
        "failure_reason",
    ]


def test_create_app_wires_forbidden_terms_from_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMHELPER_FORBIDDEN_TERMS", "sensitive, refund")
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")

    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )

    assert app.state.candidate_dispatcher.forbidden_terms == (
        "sensitive",
        "refund",
    )
    engine.dispose()


@pytest.mark.parametrize(
    ("username", "password", "expected_status"),
    [
        ("admin", "secret", 302),
        ("admin", "wrong", 400),
    ],
)
def test_single_admin_login_uses_configured_credentials(
    username: str,
    password: str,
    expected_status: int,
) -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )

    with TestClient(app, follow_redirects=False) as client:
        response = client.post(
            "/admin/login",
            data={"username": username, "password": password},
        )

    assert response.status_code == expected_status
    engine.dispose()


def test_single_admin_auth_backend_sets_and_clears_session() -> None:
    class FakeRequest:
        def __init__(self, form_data: dict[str, str]) -> None:
            self._form_data = form_data
            self.session: dict[str, str] = {}

        async def form(self) -> dict[str, str]:
            return self._form_data

    auth = SingleAdminAuth(
        AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        )
    )
    request = FakeRequest({"username": "admin", "password": "secret"})

    assert run(auth.login(request)) is True
    assert run(auth.authenticate(request)) is True
    assert run(auth.logout(request)) is True
    assert run(auth.authenticate(request)) is False


def test_create_app_uses_default_mysql_and_redis_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | None] = {}
    engine = create_engine("sqlite+pysqlite:///:memory:")

    class FakeCeleryApp:
        def send_task(
            self,
            name: str,
            *,
            kwargs: dict[str, str],
            queue: str,
        ) -> object:
            return None

    def fake_create_engine_from_url(database_url: str) -> object:
        captured["database_url"] = database_url
        return engine

    def fake_create_celery_app(
        *,
        broker_url: str,
        result_backend_url: str | None,
    ) -> FakeCeleryApp:
        captured["broker_url"] = broker_url
        captured["result_backend_url"] = result_backend_url
        return FakeCeleryApp()

    monkeypatch.setattr(web_app, "create_engine_from_url", fake_create_engine_from_url)
    monkeypatch.setattr(web_app, "create_celery_app", fake_create_celery_app)

    create_app(
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        )
    )

    assert captured == {
        "database_url": "mysql+pymysql://root:@127.0.0.1:3306/smhelper",
        "broker_url": "redis://:tbui-666@127.0.0.1:6379/0",
        "result_backend_url": "redis://:tbui-666@127.0.0.1:6379/1",
    }
    engine.dispose()
