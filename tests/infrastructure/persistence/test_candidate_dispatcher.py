from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from random import Random

from sqlalchemy.orm import Session

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.candidate_dispatcher import (
    SqlAlchemyCandidateDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    CandidateQuestionRecord,
    DispatchJobRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import SendCommentPayload
from smhelper.live.domain.account_live_session import AccountLiveSession
from smhelper.live.domain.policies.send_account_policy import SendAccountPolicy


@dataclass
class FakeBrowserTaskPublisher:
    sent: list[tuple[str, SendCommentPayload]] = field(default_factory=list)

    def send_comment(self, *, queue_name: str, payload: SendCommentPayload) -> None:
        self.sent.append((queue_name, payload))


class PreferAccountSendPolicy(SendAccountPolicy):
    def __init__(self, preferred_account_id: str) -> None:
        super().__init__(rng=Random(1))
        self.preferred_account_id = preferred_account_id

    def select_session(
        self,
        *,
        sessions: Iterable[AccountLiveSession],
        now: datetime,
    ) -> AccountLiveSession:
        session_list = list(sessions)
        return next(
            (
                session
                for session in session_list
                if session.account_id == self.preferred_account_id
            ),
            session_list[0],
        )


def test_candidate_dispatcher_approves_candidate_creates_job_and_publishes_send() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
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

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
        browser_task_publisher=publisher,
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == ["job-1"]
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
        job = session.get(DispatchJobRecord, "job-1")
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        assert candidate is not None
        assert candidate.status == "approved"
        assert candidate.reviewed_by == "admin"
        assert candidate.reviewed_at == now.replace(tzinfo=None)
        assert job is not None
        assert job.status == "running"
        assert job.started_at == now.replace(tzinfo=None)
        assert job.final_text == "Is this suitable for oily skin?"
        assert live_session is not None
        assert live_session.status == "sending"
    engine.dispose()


def test_candidate_dispatcher_skips_candidate_without_final_text() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
    with Session(engine) as session:
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
                final_text=None,
                generated_at=now,
            )
        )
        session.commit()

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
        browser_task_publisher=publisher,
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == []
    assert publisher.sent == []
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        assert candidate is not None
        assert candidate.status == "pending_review"
    engine.dispose()


def test_candidate_dispatcher_skips_candidate_when_live_task_has_ended() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
    with Session(engine) as session:
        session.add(
            LiveTaskRecord(
                id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                status="ended",
                segment_time_seconds=60,
                created_at=now,
                ended_at=now,
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

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
        browser_task_publisher=publisher,
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == []
    assert publisher.sent == []
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        jobs = session.query(DispatchJobRecord).all()
        assert candidate is not None
        assert candidate.status == "pending_review"
        assert live_session is not None
        assert live_session.status == "waiting"
        assert jobs == []
    engine.dispose()


def test_candidate_dispatcher_skips_unavailable_waiting_account() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
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
            PlatformAccountRecord(
                id="account-1",
                platform="xhs",
                display_name="Account 1",
                enabled=False,
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

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
        browser_task_publisher=publisher,
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == []
    assert publisher.sent == []
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        jobs = session.query(DispatchJobRecord).all()
        assert candidate is not None
        assert candidate.status == "pending_review"
        assert live_session is not None
        assert live_session.status == "waiting"
        assert jobs == []
    engine.dispose()


def test_candidate_dispatcher_skips_waiting_session_on_offline_worker() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
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
                online=False,
            )
        )
        session.commit()

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
        browser_task_publisher=publisher,
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == []
    assert publisher.sent == []
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        jobs = session.query(DispatchJobRecord).all()
        assert candidate is not None
        assert candidate.status == "pending_review"
        assert live_session is not None
        assert live_session.status == "waiting"
        assert jobs == []
    engine.dispose()


def test_candidate_dispatcher_skips_waiting_session_on_unsupported_worker_platform() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
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
                supported_platforms=["douyin"],
                max_browser_sessions=10,
                active_browser_sessions=1,
                online=True,
            )
        )
        session.commit()

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
        browser_task_publisher=publisher,
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == []
    assert publisher.sent == []
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        jobs = session.query(DispatchJobRecord).all()
        assert candidate is not None
        assert candidate.status == "pending_review"
        assert live_session is not None
        assert live_session.status == "waiting"
        assert jobs == []
    engine.dispose()


def test_candidate_dispatcher_uses_another_session_when_preferred_worker_is_invalid() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
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
            PlatformAccountRecord(
                id="account-bad",
                platform="xhs",
                display_name="Bad Account",
                enabled=True,
                daily_send_limit=10,
                sends_today=0,
            )
        )
        session.add(
            PlatformAccountRecord(
                id="account-good",
                platform="xhs",
                display_name="Good Account",
                enabled=True,
                daily_send_limit=10,
                sends_today=0,
            )
        )
        session.add(
            AccountAuthStateRecord(
                account_id="account-bad",
                platform="xhs",
                status="valid",
                storage_state_path="data/auth/xhs/account-bad/storage_state.json",
            )
        )
        session.add(
            AccountAuthStateRecord(
                account_id="account-good",
                platform="xhs",
                status="valid",
                storage_state_path="data/auth/xhs/account-good/storage_state.json",
            )
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-bad",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-bad",
                node_id="node-bad",
                status="waiting",
                active_slot_key="live-1:account-bad",
            )
        )
        session.add(
            AccountLiveSessionRecord(
                id="session-good",
                live_task_id="live-1",
                platform="xhs",
                room_url="https://example.com/live/1",
                account_id="account-good",
                node_id="node-good",
                status="waiting",
                active_slot_key="live-1:account-good",
            )
        )
        session.add(
            WorkerNodeRecord(
                id="node-bad",
                queue_name="node.node-bad.browser",
                supported_platforms=["douyin"],
                max_browser_sessions=10,
                active_browser_sessions=1,
                online=True,
            )
        )
        session.add(
            WorkerNodeRecord(
                id="node-good",
                queue_name="node.node-good.browser",
                supported_platforms=["xhs"],
                max_browser_sessions=10,
                active_browser_sessions=1,
                online=True,
            )
        )
        session.commit()

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=PreferAccountSendPolicy("account-bad"),
        browser_task_publisher=publisher,
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == ["job-1"]
    assert publisher.sent == [
        (
            "node.node-good.browser",
            SendCommentPayload(
                dispatch_job_id="job-1",
                session_id="session-good",
                account_id="account-good",
                final_text="Is this suitable for oily skin?",
            ),
        )
    ]
    with Session(engine) as session:
        bad_session = session.get(AccountLiveSessionRecord, "session-bad")
        good_session = session.get(AccountLiveSessionRecord, "session-good")
        assert bad_session is not None
        assert bad_session.status == "waiting"
        assert good_session is not None
        assert good_session.status == "sending"
    engine.dispose()


def test_candidate_dispatcher_keeps_candidate_pending_when_final_text_has_forbidden_term() -> (
    None
):
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    publisher = FakeBrowserTaskPublisher()
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
                question="Does this work for sensitive skin?",
                reason="The segment mentions skin type.",
                risk_level="low",
                raw_response="{}",
                status="pending_review",
                final_text="Is this suitable for sensitive skin?",
                generated_at=now,
            )
        )
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

    dispatched = SqlAlchemyCandidateDispatcher(
        session_factory=session_factory,
        ids=SequenceIdGenerator(["job-1"]),
        clock=FixedClock(now),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
        browser_task_publisher=publisher,
        forbidden_terms=("Sensitive",),
    ).approve_and_dispatch(candidate_ids=["candidate-1"], reviewed_by="admin")

    assert dispatched == []
    assert publisher.sent == []
    with Session(engine) as session:
        candidate = session.get(CandidateQuestionRecord, "candidate-1")
        live_session = session.get(AccountLiveSessionRecord, "session-1")
        jobs = session.query(DispatchJobRecord).all()
        assert candidate is not None
        assert candidate.status == "pending_review"
        assert candidate.reviewed_by is None
        assert candidate.reviewed_at is None
        assert live_session is not None
        assert live_session.status == "waiting"
        assert jobs == []
    engine.dispose()
