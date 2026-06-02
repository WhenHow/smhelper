"""Configured center worker runtime assembly."""

from __future__ import annotations

from sqlalchemy import Engine

from smhelper.core.clock import Clock, SystemClock
from smhelper.core.config import RuntimeSettings
from smhelper.core.exceptions import ConfigurationError
from smhelper.core.ids import IdGenerator, UuidGenerator
from smhelper.infrastructure.ai.litellm_question_generator import (
    LiteLLMQuestionGenerator,
)
from smhelper.infrastructure.asr.provider_adapter import (
    load_callable_speech_to_text_provider,
)
from smhelper.infrastructure.media.ffmpeg.runner import CommandRunner
from smhelper.infrastructure.persistence.sqlalchemy.base import Base
from smhelper.infrastructure.persistence.sqlalchemy.segment_processor_factory import (
    build_sqlalchemy_segment_processor,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.task_queue.celery.center_worker_runtime import (
    CenterWorkerRuntime,
    build_center_worker_runtime,
)
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry
from smhelper.live.application.ports.question_generator import QuestionGenerator
from smhelper.live.application.ports.speech_to_text import SpeechToTextProvider


def build_configured_center_worker_runtime(
    *,
    settings: RuntimeSettings | None = None,
    celery_app: CeleryTaskRegistry | None = None,
    engine: Engine | None = None,
    speech_to_text: SpeechToTextProvider | None = None,
    question_generator: QuestionGenerator | None = None,
    ids: IdGenerator | None = None,
    clock: Clock | None = None,
    command_runner: CommandRunner | None = None,
) -> CenterWorkerRuntime:
    """Build a runnable center Celery worker from runtime settings."""
    resolved_settings = settings or RuntimeSettings.from_env()
    resolved_speech_to_text = speech_to_text or _load_speech_to_text(resolved_settings)
    resolved_question_generator = question_generator or _build_question_generator(
        resolved_settings
    )
    resolved_engine = engine or create_engine_from_url(resolved_settings.database_url)
    Base.metadata.create_all(resolved_engine)
    session_factory = create_session_factory(resolved_engine)
    resolved_clock = clock or SystemClock()
    segment_processor = build_sqlalchemy_segment_processor(
        session_factory=session_factory,
        speech_to_text=resolved_speech_to_text,
        question_generator=resolved_question_generator,
        ids=ids or UuidGenerator(),
        clock=resolved_clock,
        ffmpeg_path=resolved_settings.ffmpeg_path,
        command_runner=command_runner,
    )
    return build_center_worker_runtime(
        settings=resolved_settings,
        celery_app=celery_app,
        segment_processor=segment_processor,
    )


def _load_speech_to_text(settings: RuntimeSettings) -> SpeechToTextProvider:
    if settings.asr_provider_name is None or settings.asr_provider_callable is None:
        raise ConfigurationError(
            "ASR provider name and callable must be configured for center worker"
        )
    return load_callable_speech_to_text_provider(
        provider_name=settings.asr_provider_name,
        import_path=settings.asr_provider_callable,
    )


def _build_question_generator(settings: RuntimeSettings) -> QuestionGenerator:
    if settings.llm_model is None:
        raise ConfigurationError("LLM model must be configured for center worker")
    return LiteLLMQuestionGenerator(
        model=settings.llm_model,
        fallback_models=settings.llm_fallback_models,
    )
