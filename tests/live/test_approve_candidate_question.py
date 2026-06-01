from __future__ import annotations

from datetime import UTC, datetime
from random import Random

from smhelper.core.clock import FixedClock
from smhelper.core.ids import SequenceIdGenerator
from smhelper.live.application.use_cases.approve_candidate_question import (
    ApproveCandidateQuestionUseCase,
)
from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.live.domain.candidate_question import (
    CandidateQuestion,
    CandidateQuestionStatus,
)
from smhelper.live.domain.policies.send_account_policy import SendAccountPolicy


def test_approve_candidate_question_creates_dispatch_job_for_waiting_session() -> None:
    now = datetime(2026, 6, 1, 12, 1, tzinfo=UTC)
    candidate = CandidateQuestion(
        id="candidate-1",
        live_task_id="live-1",
        segment_id="segment-1",
        question="Does this work for oily skin?",
        reason="The segment mentions skin type.",
        risk_level="low",
        raw_response="{}",
        status=CandidateQuestionStatus.PENDING_REVIEW,
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )
    session = AccountLiveSession(
        id="session-1",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.WAITING,
    )

    result = ApproveCandidateQuestionUseCase(
        clock=FixedClock(now),
        ids=SequenceIdGenerator(["job-1"]),
        send_account_policy=SendAccountPolicy(rng=Random(1)),
    ).approve(
        candidate=candidate,
        final_text="Is this suitable for oily skin?",
        reviewed_by="operator",
        sessions=[session],
    )

    assert result.candidate.status is CandidateQuestionStatus.APPROVED
    assert result.candidate.final_text == "Is this suitable for oily skin?"
    assert result.dispatch_job.id == "job-1"
    assert result.dispatch_job.account_live_session_id == "session-1"
    assert result.dispatch_job.account_id == "account-1"
    assert result.dispatch_job.final_text == "Is this suitable for oily skin?"
