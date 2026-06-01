from __future__ import annotations

from pathlib import Path

from smhelper.infrastructure.asr.provider_adapter import (
    CallableSpeechToTextProvider,
    SpeechToTextRequest,
    TranscriptionResult,
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
