from __future__ import annotations

from datetime import UTC, datetime

import pytest

from smhelper.live.domain.candidate_question import (
    CandidateQuestion,
    CandidateQuestionStatus,
    InvalidCandidateQuestion,
)
from smhelper.live.domain.dispatch_job import DispatchJob, DispatchJobStatus
from smhelper.live.domain.send_attempt import (
    SendAttempt,
    SendAttemptStatus,
    SuccessDetection,
)


def test_candidate_approval_preserves_original_question_and_records_final_text() -> (
    None
):
    generated_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    reviewed_at = datetime(2026, 6, 1, 12, 1, tzinfo=UTC)
    candidate = CandidateQuestion(
        id="candidate-1",
        live_task_id="live-1",
        segment_id="segment-1",
        question="Does this work for oily skin?",
        reason="The segment mentions skin type.",
        risk_level="low",
        raw_response='{"question":"Does this work for oily skin?"}',
        status=CandidateQuestionStatus.PENDING_REVIEW,
        generated_at=generated_at,
    )

    approved = candidate.approve(
        final_text="Is this suitable for oily skin?",
        reviewed_by="operator",
        reviewed_at=reviewed_at,
    )

    assert approved.question == "Does this work for oily skin?"
    assert approved.final_text == "Is this suitable for oily skin?"
    assert approved.status is CandidateQuestionStatus.APPROVED
    assert approved.reviewed_by == "operator"
    assert approved.reviewed_at == reviewed_at


def test_candidate_reject_records_reason_without_final_text() -> None:
    generated_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    reviewed_at = datetime(2026, 6, 1, 12, 1, tzinfo=UTC)
    candidate = CandidateQuestion(
        id="candidate-1",
        live_task_id="live-1",
        segment_id="segment-1",
        question="Unrelated question?",
        reason="weak context",
        risk_level="medium",
        raw_response="{}",
        status=CandidateQuestionStatus.PENDING_REVIEW,
        generated_at=generated_at,
    )

    rejected = candidate.reject(
        reason="not product related",
        reviewed_by="operator",
        reviewed_at=reviewed_at,
    )

    assert rejected.status is CandidateQuestionStatus.REJECTED
    assert rejected.rejection_reason == "not product related"
    assert rejected.final_text is None


def test_candidate_approval_requires_non_blank_final_text() -> None:
    candidate = CandidateQuestion(
        id="candidate-1",
        live_task_id="live-1",
        segment_id="segment-1",
        question="Question?",
        reason="reason",
        risk_level="low",
        raw_response="{}",
        status=CandidateQuestionStatus.PENDING_REVIEW,
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(InvalidCandidateQuestion):
        candidate.approve(
            final_text=" ",
            reviewed_by="operator",
            reviewed_at=datetime(2026, 6, 1, 12, 1, tzinfo=UTC),
        )


def test_candidate_approval_requires_pending_review_status() -> None:
    candidate = CandidateQuestion(
        id="candidate-1",
        live_task_id="live-1",
        segment_id="segment-1",
        question="Question?",
        reason="reason",
        risk_level="low",
        raw_response="{}",
        status=CandidateQuestionStatus.PARSE_FAILED,
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(InvalidCandidateQuestion, match="pending review"):
        candidate.approve(
            final_text="Is this suitable?",
            reviewed_by="operator",
            reviewed_at=datetime(2026, 6, 1, 12, 1, tzinfo=UTC),
        )


def test_candidate_reject_requires_pending_review_status() -> None:
    candidate = CandidateQuestion(
        id="candidate-1",
        live_task_id="live-1",
        segment_id="segment-1",
        question="Question?",
        reason="reason",
        risk_level="low",
        raw_response="{}",
        status=CandidateQuestionStatus.APPROVED,
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(InvalidCandidateQuestion, match="pending review"):
        candidate.reject(
            reason="not useful",
            reviewed_by="operator",
            reviewed_at=datetime(2026, 6, 1, 12, 1, tzinfo=UTC),
        )


def test_candidate_approval_rejects_forbidden_terms() -> None:
    candidate = CandidateQuestion(
        id="candidate-1",
        live_task_id="live-1",
        segment_id="segment-1",
        question="Question?",
        reason="reason",
        risk_level="low",
        raw_response="{}",
        status=CandidateQuestionStatus.PENDING_REVIEW,
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(InvalidCandidateQuestion, match="forbidden term"):
        candidate.approve(
            final_text="Can it repair sensitive skin?",
            reviewed_by="operator",
            reviewed_at=datetime(2026, 6, 1, 12, 1, tzinfo=UTC),
            forbidden_terms=("Sensitive",),
        )


def test_dispatch_job_uses_approved_final_text() -> None:
    created_at = datetime(2026, 6, 1, 12, 2, tzinfo=UTC)

    job = DispatchJob.create(
        id="job-1",
        candidate_question_id="candidate-1",
        live_task_id="live-1",
        account_live_session_id="session-1",
        account_id="account-1",
        final_text="Is this suitable for oily skin?",
        created_at=created_at,
    )

    assert job.status is DispatchJobStatus.PENDING
    assert job.final_text == "Is this suitable for oily skin?"
    assert job.created_at == created_at


def test_send_attempt_success_uses_operation_completed_detection() -> None:
    sent_at = datetime(2026, 6, 1, 12, 3, tzinfo=UTC)

    attempt = SendAttempt.success(
        id="attempt-1",
        dispatch_job_id="job-1",
        account_live_session_id="session-1",
        account_id="account-1",
        sent_at=sent_at,
    )

    assert attempt.status is SendAttemptStatus.SUCCESS
    assert attempt.success_detection is SuccessDetection.OPERATION_COMPLETED
    assert attempt.failure_reason is None
