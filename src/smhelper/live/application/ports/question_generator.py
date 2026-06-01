"""Port for generating candidate questions from transcript context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class QuestionGenerationPrompt:
    """Inputs used to generate a candidate live-room question."""

    product_context: str
    recent_transcript: str
    task_context: str


@dataclass(frozen=True, slots=True)
class GeneratedQuestionDraft:
    """Parsed LLM candidate question before persistence."""

    question: str
    reason: str
    risk_level: str
    raw_response: str
    parse_warning: str | None = None


class QuestionGenerator(Protocol):
    """Generates one candidate live-room question."""

    def generate(self, prompt: QuestionGenerationPrompt) -> GeneratedQuestionDraft:
        """Generate and parse one candidate question."""
