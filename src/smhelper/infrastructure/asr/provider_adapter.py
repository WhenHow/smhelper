"""Generic adapter boundary for vendor ASR providers."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import cast

from smhelper.core.exceptions import ConfigurationError
from smhelper.live.application.ports.speech_to_text import (
    SpeechToTextProvider,
    SpeechToTextRequest,
    TranscriptionResult,
)

__all__ = [
    "CallableSpeechToTextProvider",
    "SpeechToTextProvider",
    "SpeechToTextRequest",
    "TranscriptionResult",
    "load_callable_speech_to_text_provider",
]


class CallableSpeechToTextProvider:
    """Wrap a vendor callable behind the project ASR interface."""

    def __init__(
        self,
        *,
        provider_name: str,
        transcribe: Callable[[SpeechToTextRequest], TranscriptionResult],
    ) -> None:
        self.provider_name = provider_name
        self._transcribe = transcribe

    def transcribe(self, request: SpeechToTextRequest) -> TranscriptionResult:
        """Transcribe audio through the configured vendor callable."""
        return self._transcribe(request)


def load_callable_speech_to_text_provider(
    *,
    provider_name: str,
    import_path: str,
) -> CallableSpeechToTextProvider:
    """Load a vendor transcribe callable from ``module:function`` import path."""
    module_name, separator, attribute_name = import_path.strip().partition(":")
    if not module_name or separator != ":" or not attribute_name:
        raise ConfigurationError(
            "ASR provider callable must use module:function import path"
        )
    try:
        module = import_module(module_name)
        candidate = getattr(module, attribute_name)
    except (ImportError, AttributeError) as exc:
        raise ConfigurationError(
            f"ASR provider callable cannot be loaded: {import_path}"
        ) from exc
    if not callable(candidate):
        raise ConfigurationError(
            f"ASR provider callable is not callable: {import_path}"
        )
    transcribe = cast(Callable[[SpeechToTextRequest], TranscriptionResult], candidate)
    return CallableSpeechToTextProvider(
        provider_name=provider_name,
        transcribe=transcribe,
    )
