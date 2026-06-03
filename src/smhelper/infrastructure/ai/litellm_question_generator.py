"""LiteLLM-backed candidate question generator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from json import JSONDecodeError, dumps, loads
from os import environ
from typing import cast

from smhelper.core.exceptions import SmHelperError
from smhelper.live.application.ports.question_generator import (
    GeneratedQuestionDraft,
    QuestionGenerationPrompt,
)


class QuestionGenerationError(SmHelperError):
    """Raised when an LLM response cannot produce a usable candidate question."""


CompletionCallable = Callable[..., object]


@dataclass(frozen=True, slots=True)
class LiteLLMQuestionGenerator:
    """Generate one JSON candidate question through the LiteLLM Python SDK."""

    model: str
    fallback_models: tuple[str, ...] = ()
    completion: CompletionCallable | None = None

    def generate(self, prompt: QuestionGenerationPrompt) -> GeneratedQuestionDraft:
        """Call the configured model and parse exactly one candidate question."""
        environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        messages = self._messages(prompt)
        last_error: Exception | None = None
        for model in (self.model, *self.fallback_models):
            try:
                response = self._completion()(
                    model=model,
                    messages=messages,
                )
            except Exception as exc:  # noqa: BLE001 - provider errors are recorded here.
                last_error = exc
                continue
            content = self._extract_content(response)
            return self._parse_content(content)

        raise QuestionGenerationError("LLM completion failed") from last_error

    def _completion(self) -> CompletionCallable:
        if self.completion is not None:
            return self.completion
        from litellm import completion

        return cast(CompletionCallable, completion)

    @staticmethod
    def _messages(prompt: QuestionGenerationPrompt) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Generate exactly one product-related live-room question. "
                    "Return JSON with question, reason and risk_level."
                ),
            },
            {
                "role": "user",
                "content": dumps(
                    {
                        "product_context": prompt.product_context,
                        "recent_transcript": prompt.recent_transcript,
                        "task_context": prompt.task_context,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _extract_content(self, response: object) -> str:
        dumped_response = self._dump_response(response)
        choices = dumped_response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise QuestionGenerationError("LLM response does not contain choices")
        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise QuestionGenerationError("LLM response choice is not an object")
        message = first_choice.get("message")
        if not isinstance(message, Mapping):
            raise QuestionGenerationError(
                "LLM response choice does not contain message"
            )
        content = message.get("content")
        if not isinstance(content, str):
            raise QuestionGenerationError("LLM response message content is not text")
        return content

    def _dump_response(self, response: object) -> Mapping[str, object]:
        if isinstance(response, Mapping):
            return response
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, Mapping):
                return dumped
        raise QuestionGenerationError("LLM response cannot be inspected")

    def _parse_content(self, content: str) -> GeneratedQuestionDraft:
        try:
            parsed = loads(content)
        except JSONDecodeError as exc:
            raise QuestionGenerationError("Failed to parse LLM JSON response") from exc
        if not isinstance(parsed, Mapping):
            raise QuestionGenerationError("Parsed LLM response is not an object")

        if "questions" in parsed:
            raise QuestionGenerationError(
                "LLM response must be a single JSON object, not a candidate list"
            )

        question = self._required_text(parsed, "question")
        reason = self._required_text(parsed, "reason")
        risk_level = self._required_text(parsed, "risk_level")
        return GeneratedQuestionDraft(
            question=question,
            reason=reason,
            risk_level=risk_level,
            raw_response=content,
            parse_warning=None,
        )

    @staticmethod
    def _required_text(source: Mapping[str, object], key: str) -> str:
        value = source.get(key)
        if not isinstance(value, str) or not value.strip():
            raise QuestionGenerationError(f"LLM response missing {key!r}")
        return value.strip()
