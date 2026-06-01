from __future__ import annotations

from os import environ
from dataclasses import dataclass, field

import pytest

from smhelper.infrastructure.ai.litellm_question_generator import (
    LiteLLMQuestionGenerator,
    QuestionGenerationError,
    QuestionGenerationPrompt,
)


@dataclass
class FakeCompletion:
    responses: list[object]
    calls: list[str] = field(default_factory=list)

    def __call__(self, *, model: str, messages: list[dict[str, str]]) -> object:
        self.calls.append(model)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_litellm_question_generator_sets_local_cost_map_and_parses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LITELLM_LOCAL_MODEL_COST_MAP", raising=False)
    completion = FakeCompletion(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"question":"Is this suitable for oily skin?",'
                                '"reason":"The transcript mentions skin type.",'
                                '"risk_level":"low"}'
                            )
                        }
                    }
                ]
            }
        ]
    )

    draft = LiteLLMQuestionGenerator(
        model="openai/gpt-4.1-mini",
        completion=completion,
    ).generate(
        QuestionGenerationPrompt(
            product_context="Face cream for oily skin.",
            recent_transcript="The host is talking about texture.",
            task_context="Ask product-related questions.",
        )
    )

    assert draft.question == "Is this suitable for oily skin?"
    assert draft.reason == "The transcript mentions skin type."
    assert draft.risk_level == "low"
    assert draft.parse_warning is None
    assert completion.calls == ["openai/gpt-4.1-mini"]
    assert environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "True"


def test_litellm_question_generator_uses_first_candidate_when_model_returns_list() -> (
    None
):
    completion = FakeCompletion(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"questions":['
                                '{"question":"First?","reason":"r1","risk_level":"low"},'
                                '{"question":"Second?","reason":"r2","risk_level":"low"}'
                                "]} "
                            )
                        }
                    }
                ]
            }
        ]
    )

    draft = LiteLLMQuestionGenerator(
        model="openai/gpt-4.1-mini",
        completion=completion,
    ).generate(
        QuestionGenerationPrompt(
            product_context="Product",
            recent_transcript="Transcript",
            task_context="Context",
        )
    )

    assert draft.question == "First?"
    assert draft.parse_warning == "multiple_candidates_returned"


def test_litellm_question_generator_tries_fallback_model_after_primary_error() -> None:
    completion = FakeCompletion(
        responses=[
            RuntimeError("primary down"),
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"question":"Fallback?","reason":"r","risk_level":"low"}'
                            )
                        }
                    }
                ]
            },
        ]
    )

    draft = LiteLLMQuestionGenerator(
        model="primary",
        fallback_models=("fallback",),
        completion=completion,
    ).generate(
        QuestionGenerationPrompt(
            product_context="Product",
            recent_transcript="Transcript",
            task_context="Context",
        )
    )

    assert draft.question == "Fallback?"
    assert completion.calls == ["primary", "fallback"]


def test_litellm_question_generator_raises_when_response_is_not_valid_json() -> None:
    completion = FakeCompletion(
        responses=[{"choices": [{"message": {"content": "not-json"}}]}]
    )

    with pytest.raises(QuestionGenerationError, match="parse"):
        LiteLLMQuestionGenerator(
            model="primary",
            completion=completion,
        ).generate(
            QuestionGenerationPrompt(
                product_context="Product",
                recent_transcript="Transcript",
                task_context="Context",
            )
        )
