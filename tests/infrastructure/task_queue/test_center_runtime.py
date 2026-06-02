from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

from smhelper.core.config import RuntimeSettings
from smhelper.core.exceptions import ConfigurationError
from smhelper.infrastructure.ai.litellm_question_generator import (
    LiteLLMQuestionGenerator,
)
from smhelper.infrastructure.asr.provider_adapter import (
    CallableSpeechToTextProvider,
)
from smhelper.infrastructure.media.ffmpeg.artifact_extractor import (
    FFmpegMediaArtifactExtractor,
)
from smhelper.infrastructure.media.ffmpeg.runner import CommandRunner
from smhelper.infrastructure.persistence.sqlalchemy.segment_processor import (
    SqlAlchemySegmentProcessor,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_observer import (
    SqlAlchemyLiveTaskObserverRunner,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_starter import (
    SqlAlchemyLiveTaskStarter,
)
from smhelper.infrastructure.persistence.sqlalchemy.live_task_terminator import (
    SqlAlchemyLiveTaskTerminator,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.infrastructure.task_queue.celery import center_runtime
from smhelper.infrastructure.task_queue.celery.center_runtime import (
    build_configured_center_worker_runtime,
)
from smhelper.infrastructure.task_queue.celery.tasks import (
    OBSERVE_LIVE_TASK_TASK,
    PROCESS_SEGMENT_TASK,
)
from smhelper.live.application.ports.speech_to_text import (
    SpeechToTextRequest,
    TranscriptionResult,
)
from smhelper.live.application.use_cases.process_segment import ProcessSegmentUseCase
from smhelper.platforms.xhs.browser.cloakbrowser_observer import (
    XhsCloakBrowserLiveStreamObserver,
)


@dataclass
class FakeCeleryApp:
    tasks: dict[str, Callable[..., None]] = field(default_factory=dict)

    def task(
        self,
        *,
        name: str,
    ) -> Callable[[Callable[..., None]], Callable[..., None]]:
        def register(func: Callable[..., None]) -> Callable[..., None]:
            self.tasks[name] = func
            return func

        return register


@dataclass
class FakeCommandRunner(CommandRunner):
    commands: list[list[str]] = field(default_factory=list)

    def run(self, command: list[str]) -> None:
        self.commands.append(command)


@dataclass
class FakeProcessStarter:
    commands: list[list[str]] = field(default_factory=list)

    def start(self, command: list[str]) -> None:
        self.commands.append(command)


def test_build_configured_center_worker_runtime_wires_segment_processor(
    tmp_path: Path,
) -> None:
    settings = _settings(
        tmp_path,
        {
            "SMHELPER_FFMPEG_PATH": "ffmpeg-custom",
            "SMHELPER_LLM_MODEL": "vendor/main-model",
            "SMHELPER_LLM_FALLBACK_MODELS": "vendor/fallback",
            "SMHELPER_ASR_PROVIDER_NAME": "vendor-a",
            "SMHELPER_ASR_PROVIDER_CALLABLE": (
                "test_center_runtime:fake_vendor_transcribe"
            ),
        },
    )
    celery_app = FakeCeleryApp()
    command_runner = FakeCommandRunner()
    process_starter = FakeProcessStarter()
    engine = create_engine_from_url(settings.database_url)

    try:
        runtime = build_configured_center_worker_runtime(
            settings=settings,
            celery_app=celery_app,
            engine=engine,
            command_runner=command_runner,
            process_starter=process_starter,
        )

        assert runtime.celery_app is celery_app
        assert set(celery_app.tasks) == {
            PROCESS_SEGMENT_TASK,
            OBSERVE_LIVE_TASK_TASK,
        }
        assert isinstance(runtime.handler.segment_processor, SqlAlchemySegmentProcessor)
        use_case = runtime.handler.segment_processor.processor
        assert isinstance(use_case, ProcessSegmentUseCase)
        assert isinstance(use_case.speech_to_text, CallableSpeechToTextProvider)
        assert use_case.speech_to_text.provider_name == "vendor-a"
        assert isinstance(use_case.question_generator, LiteLLMQuestionGenerator)
        assert use_case.question_generator.model == "vendor/main-model"
        assert use_case.question_generator.fallback_models == ("vendor/fallback",)
        assert isinstance(use_case.media_artifacts, FFmpegMediaArtifactExtractor)
        assert use_case.media_artifacts.ffmpeg_path == "ffmpeg-custom"
        assert use_case.media_artifacts.command_runner is command_runner
        observer_runner = runtime.handler.live_task_observer_runner
        assert isinstance(observer_runner, SqlAlchemyLiveTaskObserverRunner)
        assert isinstance(observer_runner.observer, XhsCloakBrowserLiveStreamObserver)
        assert isinstance(observer_runner.starter, SqlAlchemyLiveTaskStarter)
        assert observer_runner.starter.process_starter is process_starter
        assert observer_runner.starter.media_root == settings.media_root
        assert observer_runner.starter.ffmpeg_path == "ffmpeg-custom"
        assert isinstance(observer_runner.terminator, SqlAlchemyLiveTaskTerminator)
    finally:
        engine.dispose()


def test_build_configured_center_worker_runtime_requires_llm_model(
    tmp_path: Path,
) -> None:
    settings = _settings(
        tmp_path,
        {
            "SMHELPER_ASR_PROVIDER_NAME": "vendor-a",
            "SMHELPER_ASR_PROVIDER_CALLABLE": (
                "test_center_runtime:fake_vendor_transcribe"
            ),
        },
    )

    with pytest.raises(ConfigurationError, match="LLM model"):
        build_configured_center_worker_runtime(
            settings=settings,
            celery_app=FakeCeleryApp(),
        )


def test_build_configured_center_worker_runtime_validates_before_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(
        tmp_path,
        {
            "SMHELPER_ASR_PROVIDER_NAME": "vendor-a",
            "SMHELPER_ASR_PROVIDER_CALLABLE": (
                "test_center_runtime:fake_vendor_transcribe"
            ),
        },
    )

    def fail_if_called(database_url: str):
        raise AssertionError(f"database should not be created: {database_url}")

    monkeypatch.setattr(center_runtime, "create_engine_from_url", fail_if_called)

    with pytest.raises(ConfigurationError, match="LLM model"):
        build_configured_center_worker_runtime(
            settings=settings,
            celery_app=FakeCeleryApp(),
        )


def test_build_configured_center_worker_runtime_requires_asr_provider(
    tmp_path: Path,
) -> None:
    settings = _settings(
        tmp_path,
        {
            "SMHELPER_LLM_MODEL": "vendor/main-model",
        },
    )

    with pytest.raises(ConfigurationError, match="ASR provider"):
        build_configured_center_worker_runtime(
            settings=settings,
            celery_app=FakeCeleryApp(),
        )


def fake_vendor_transcribe(request: SpeechToTextRequest) -> TranscriptionResult:
    return TranscriptionResult(
        text=f"loaded text from {request.audio_path.name}",
        provider_name="vendor-a",
        raw_response='{"ok":true}',
    )


def _settings(tmp_path: Path, overrides: dict[str, str]) -> RuntimeSettings:
    env = {
        "SMHELPER_DATABASE_URL": f"sqlite+pysqlite:///{tmp_path / 'smhelper.db'}",
        "SMHELPER_CELERY_BROKER_URL": "redis://:secret@redis:6379/0",
        "SMHELPER_CELERY_RESULT_BACKEND_URL": "redis://:secret@redis:6379/1",
        **overrides,
    }
    return RuntimeSettings.from_env(env, cwd=tmp_path)
