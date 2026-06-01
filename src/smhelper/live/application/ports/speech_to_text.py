"""Port for speech-to-text providers."""

from __future__ import annotations

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
