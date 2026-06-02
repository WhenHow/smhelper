from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    CandidateQuestionRecord,
    DispatchJobRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import SendCommentPayload
from smhelper.web.admin import AdminCredentials
from smhelper.web.app import create_app


@dataclass
class FakeBrowserTaskPublisher:
    sent: list[tuple[str, SendCommentPayload]] = field(default_factory=list)

    def send_comment(self, *, queue_name: str, payload: SendCommentPayload) -> None:
        self.sent.append((queue_name, payload))


def test_sqladmin_candidate_approve_action_dispatches_send_job(tmp_path: Path) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    Base.metadata.create_all(engine)
    publisher = FakeBrowserTaskPublisher()
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
        browser_task_publisher=publisher,
        ids=SequenceIdGenerator(["job-1"]),
    )
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
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
            CandidateQuestionRecord(
                id="candidate-1",
                live_task_id="live-1",
                segment_id="segment-1",
                question="Does this work for oily skin?",
                reason="The segment mentions skin type.",
                risk_level="low",
                raw_response="{}",
                status="pending_review",
                final_text="Is this suitable for oily skin?",
                generated_at=now,
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
                active_slot_key="live-1:account-1",
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
        session.commit()

    with TestClient(app, follow_redirects=False) as client:
        client.post(
            "/admin/login",
            data={"username": "admin", "password": "secret"},
        )
        response = client.get(
            "/admin/candidate-question-record/action/approve?pks=candidate-1",
            headers={"Referer": "/admin/candidate-question-record/list"},
        )

    assert response.status_code == 302
    assert publisher.sent == [
        (
            "node.node-a.browser",
            SendCommentPayload(
                dispatch_job_id="job-1",
                session_id="session-1",
                account_id="account-1",
                final_text="Is this suitable for oily skin?",
            ),
        )
    ]
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        jobs = session.query(DispatchJobRecord).all()
        assert candidate is not None
        assert candidate.status == "approved"
        assert len(jobs) == 1
        assert jobs[0].final_text == "Is this suitable for oily skin?"
    engine.dispose()


def test_sqladmin_candidate_reject_action_marks_pending_candidates_rejected(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    Base.metadata.create_all(engine)
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
        browser_task_publisher=FakeBrowserTaskPublisher(),
    )
    generated_at = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            CandidateQuestionRecord(
                id="candidate-1",
                live_task_id="live-1",
                segment_id="segment-1",
                question="Unrelated question?",
                reason="weak context",
                risk_level="medium",
                raw_response="{}",
                status="pending_review",
                final_text="Unrelated question?",
                generated_at=generated_at,
            )
        )
        session.commit()

    with TestClient(app, follow_redirects=False) as client:
        client.post(
            "/admin/login",
            data={"username": "admin", "password": "secret"},
        )
        response = client.get(
            "/admin/candidate-question-record/action/reject?pks=candidate-1",
            headers={"Referer": "/admin/candidate-question-record/list"},
        )

    assert response.status_code == 302
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        assert candidate is not None
        assert candidate.status == "rejected"
        assert candidate.final_text is None
        assert candidate.reviewed_by == "admin"
        assert candidate.reviewed_at is not None
        assert candidate.rejection_reason == "operator_rejected"
    engine.dispose()
