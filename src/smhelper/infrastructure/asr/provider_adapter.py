"""Generic adapter boundary for vendor ASR providers."""

from __future__ import annotations

from collections.abc import Callable

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
