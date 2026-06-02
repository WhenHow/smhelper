from __future__ import annotations

from pathlib import Path

import pytest

from smhelper.core.exceptions import ConfigurationError
from smhelper.infrastructure.asr.provider_adapter import (
    CallableSpeechToTextProvider,
    SpeechToTextRequest,
    TranscriptionResult,
    load_callable_speech_to_text_provider,
)


def test_callable_speech_to_text_provider_wraps_vendor_function(tmp_path: Path) -> None:
    audio_path = tmp_path / "segment.wav"
    audio_path.write_bytes(b"fake")

    provider = CallableSpeechToTextProvider(
        provider_name="vendor-a",
        transcribe=lambda request: TranscriptionResult(
            text=f"text from {request.audio_path.name}",
            provider_name="vendor-a",
            raw_response='{"ok":true}',
        ),
    )

    result = provider.transcribe(SpeechToTextRequest(audio_path=audio_path))

    assert result.text == "text from segment.wav"
    assert result.provider_name == "vendor-a"
    assert result.raw_response == '{"ok":true}'


def test_load_callable_speech_to_text_provider_from_import_path(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "segment.wav"
    audio_path.write_bytes(b"fake")

    provider = load_callable_speech_to_text_provider(
        provider_name="vendor-a",
        import_path="test_provider_adapter:fake_vendor_transcribe",
    )

    result = provider.transcribe(SpeechToTextRequest(audio_path=audio_path))

    assert result.text == "loaded text from segment.wav"
    assert result.provider_name == "vendor-a"


def test_load_callable_speech_to_text_provider_rejects_invalid_import_path() -> None:
    with pytest.raises(ConfigurationError, match="ASR provider callable"):
        load_callable_speech_to_text_provider(
            provider_name="vendor-a",
            import_path="missing.module:function",
        )


def fake_vendor_transcribe(request: SpeechToTextRequest) -> TranscriptionResult:
    return TranscriptionResult(
        text=f"loaded text from {request.audio_path.name}",
        provider_name="vendor-a",
        raw_response='{"loaded":true}',
    )
