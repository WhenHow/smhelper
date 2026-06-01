"""Generic adapter boundary for vendor ASR providers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SpeechToTextRequest:
    """Request to transcribe one extracted audio file."""

    audio_path: Path
    language: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """Normalized transcription result from a vendor ASR provider."""

    text: str
    provider_name: str
    raw_response: str


class SpeechToTextProvider(Protocol):
    """Application-facing speech-to-text adapter."""

    def transcribe(self, request: SpeechToTextRequest) -> TranscriptionResult:
        """Transcribe an audio file."""


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
