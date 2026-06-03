"""Candidate question domain model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from smhelper.core.exceptions import SmHelperError


class InvalidCandidateQuestion(SmHelperError):
    """Raised when candidate question data violates review rules."""


class CandidateQuestionStatus(str, Enum):
    """Review status of an LLM-generated candidate question."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IGNORED = "ignored"
    PARSE_FAILED = "parse_failed"


@dataclass(frozen=True, slots=True)
class CandidateQuestion:
    """LLM-generated question awaiting operator review."""

    id: str
    live_task_id: str
    segment_id: str
    question: str
    reason: str
    risk_level: str
    raw_response: str
    status: CandidateQuestionStatus
    generated_at: datetime
    final_text: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None

    def approve(
        self,
        *,
        final_text: str,
        reviewed_by: str,
        reviewed_at: datetime,
        forbidden_terms: tuple[str, ...] = (),
    ) -> CandidateQuestion:
        """Return an approved candidate while preserving the original LLM text."""
        self._ensure_pending_review()
        normalized_final_text = final_text.strip()
        if not normalized_final_text:
            raise InvalidCandidateQuestion("approved final text must not be blank")
        matched_term = _find_forbidden_term(
            text=normalized_final_text,
            forbidden_terms=forbidden_terms,
        )
        if matched_term is not None:
            raise InvalidCandidateQuestion(
                f"approved final text contains forbidden term: {matched_term}"
            )
        return replace(
            self,
            status=CandidateQuestionStatus.APPROVED,
            final_text=normalized_final_text,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            rejection_reason=None,
        )

    def reject(
        self,
        *,
        reason: str,
        reviewed_by: str,
        reviewed_at: datetime,
    ) -> CandidateQuestion:
        """Return a rejected candidate with an operator reason."""
        self._ensure_pending_review()
        return replace(
            self,
            status=CandidateQuestionStatus.REJECTED,
            final_text=None,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            rejection_reason=reason.strip() or None,
        )

    def ignore(
        self,
        *,
        reviewed_by: str,
        reviewed_at: datetime,
    ) -> CandidateQuestion:
        """Return an ignored candidate without treating it as rejected."""
        self._ensure_pending_review()
        return replace(
            self,
            status=CandidateQuestionStatus.IGNORED,
            final_text=None,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            rejection_reason=None,
        )

    def _ensure_pending_review(self) -> None:
        """Ensure review actions only apply to pending candidates."""
        if self.status is not CandidateQuestionStatus.PENDING_REVIEW:
            raise InvalidCandidateQuestion(
                "candidate must be pending review before operator review"
            )


def _find_forbidden_term(
    *,
    text: str,
    forbidden_terms: tuple[str, ...],
) -> str | None:
    """Return the first configured forbidden term found in text."""
    normalized_text = text.casefold()
    for term in forbidden_terms:
        normalized_term = term.strip()
        if normalized_term and normalized_term.casefold() in normalized_text:
            return normalized_term
    return None
