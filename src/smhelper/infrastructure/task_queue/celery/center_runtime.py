"""Configured center worker runtime assembly."""

from __future__ import annotations

from random import Random
from typing import cast

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
from smhelper.infrastructure.media.ffmpeg.runner import (
    BackgroundProcessStarter,
    CommandRunner,
    SubprocessBackgroundProcessStarter,
)
from smhelper.infrastructure.persistence.sqlalchemy.account_entry_dispatcher import (
    SqlAlchemyAccountEntryDispatcher,
)
from smhelper.infrastructure.persistence.sqlalchemy.account_entry_planner import (
    SqlAlchemyAccountEntryPlanner,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_observer import (
    SqlAlchemyLiveTaskObserverRunner,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_shutdown_coordinator import (
    SqlAlchemyLiveTaskShutdownCoordinator,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_starter import (
    SqlAlchemyLiveTaskStarter,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_terminator import (
    SqlAlchemyLiveTaskTerminator,
)
from smhelper.infrastructure.persistence.sqlalchemy.segment_processor_factory import (
    build_sqlalchemy_segment_processor,
)
from smhelper.infrastructure.persistence.sqlalchemy.segment_task_scheduler import (
    SqlAlchemySegmentTaskScheduler,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
    create_session_factory,
)
from smhelper.infrastructure.persistence.sqlalchemy.schema import create_database_schema
from smhelper.infrastructure.task_queue.celery.app import create_celery_app
from smhelper.infrastructure.task_queue.celery.center_publisher import (
    CenterTaskPublisher,
)
from smhelper.infrastructure.task_queue.celery.center_worker_runtime import (
    CenterWorkerRuntime,
    build_center_worker_runtime,
)
from smhelper.infrastructure.task_queue.celery.node_tasks import CeleryTaskRegistry
from smhelper.infrastructure.task_queue.celery.publisher import (
    BrowserTaskPublisher,
    CeleryTaskSender,
)
from smhelper.live.application.ports.live_stream_observer import LiveStreamObserver
from smhelper.live.application.ports.question_generator import QuestionGenerator
from smhelper.live.application.ports.speech_to_text import SpeechToTextProvider
from smhelper.live.application.use_cases.plan_account_entries import (
    PlanAccountEntriesUseCase,
)
from smhelper.live.domain.policies.shutdown_policy import LiveTaskShutdownPolicy
from smhelper.platforms.xhs.browser.cloakbrowser_observer import (
    XhsCloakBrowserLiveStreamObserver,
)
from smhelper.workers.domain.rendezvous_hashing import RendezvousHashingNodeSelector


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
    process_starter: BackgroundProcessStarter | None = None,
    live_stream_observer: LiveStreamObserver | None = None,
) -> CenterWorkerRuntime:
    """Build a runnable center Celery worker from runtime settings."""
    resolved_settings = settings or RuntimeSettings.from_env()
    resolved_speech_to_text = speech_to_text or _load_speech_to_text(resolved_settings)
    resolved_question_generator = question_generator or _build_question_generator(
        resolved_settings
    )
    resolved_celery_app = celery_app or cast(
        CeleryTaskRegistry,
        create_celery_app(
            broker_url=resolved_settings.celery_broker_url,
            result_backend_url=resolved_settings.celery_result_backend_url,
        ),
    )
    resolved_engine = engine or create_engine_from_url(resolved_settings.database_url)
    create_database_schema(engine=resolved_engine)
    session_factory = create_session_factory(resolved_engine)
    resolved_clock = clock or SystemClock()
    resolved_ids = ids or UuidGenerator()
    segment_processor = build_sqlalchemy_segment_processor(
        session_factory=session_factory,
        speech_to_text=resolved_speech_to_text,
        question_generator=resolved_question_generator,
        ids=resolved_ids,
        clock=resolved_clock,
        ffmpeg_path=resolved_settings.ffmpeg_path,
        command_runner=command_runner,
    )
    browser_task_publisher = BrowserTaskPublisher(
        celery_app=cast(CeleryTaskSender, resolved_celery_app),
    )
    center_task_publisher = CenterTaskPublisher(
        celery_app=cast(CeleryTaskSender, resolved_celery_app),
    )
    account_entry_planner = SqlAlchemyAccountEntryPlanner(
        session_factory=session_factory,
        clock=resolved_clock,
        planner=PlanAccountEntriesUseCase(
            selector=RendezvousHashingNodeSelector(),
            ids=resolved_ids,
            rng=Random(),
        ),
        dispatcher=SqlAlchemyAccountEntryDispatcher(
            session_factory=session_factory,
            browser_task_publisher=browser_task_publisher,
        ),
    )
    shutdown_coordinator = SqlAlchemyLiveTaskShutdownCoordinator(
        session_factory=session_factory,
        clock=resolved_clock,
        shutdown_policy=LiveTaskShutdownPolicy(),
        browser_task_publisher=browser_task_publisher,
    )
    live_task_observer_runner = SqlAlchemyLiveTaskObserverRunner(
        session_factory=session_factory,
        observer=live_stream_observer or XhsCloakBrowserLiveStreamObserver(),
        starter=SqlAlchemyLiveTaskStarter(
            session_factory=session_factory,
            clock=resolved_clock,
            process_starter=process_starter or SubprocessBackgroundProcessStarter(),
            account_entry_planner=account_entry_planner,
            media_root=resolved_settings.media_root,
            ffmpeg_path=resolved_settings.ffmpeg_path,
        ),
        terminator=SqlAlchemyLiveTaskTerminator(
            session_factory=session_factory,
            clock=resolved_clock,
            shutdown_coordinator=shutdown_coordinator,
        ),
        segment_scheduler=SqlAlchemySegmentTaskScheduler(
            session_factory=session_factory,
            ids=resolved_ids,
            clock=resolved_clock,
            publisher=center_task_publisher,
            media_root=resolved_settings.media_root,
            queue_name=resolved_settings.center_queue_name,
        ),
    )
    return build_center_worker_runtime(
        settings=resolved_settings,
        celery_app=resolved_celery_app,
        segment_processor=segment_processor,
        live_task_observer_runner=live_task_observer_runner,
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
