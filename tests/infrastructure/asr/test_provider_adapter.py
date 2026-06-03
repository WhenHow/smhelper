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


def test_loads_builtin_local_asr_provider_from_import_path(tmp_path: Path) -> None:
    audio_path = tmp_path / "segment.wav"
    transcript_path = tmp_path / "segment.txt"
    audio_path.write_bytes(b"fake")
    transcript_path.write_text("主播刚才提到了敏感肌和保湿。", encoding="utf-8")

    provider = load_callable_speech_to_text_provider(
        provider_name="local-dev",
        import_path="smhelper.infrastructure.asr.local_provider:transcribe",
    )

    result = provider.transcribe(SpeechToTextRequest(audio_path=audio_path))

    assert result.text == "主播刚才提到了敏感肌和保湿。"
    assert result.provider_name == "local-dev"
    assert result.raw_response == (
        '{"source":"adjacent_text","path":"'
        + str(transcript_path).replace("\\", "\\\\")
        + '"}'
    )


def test_builtin_local_asr_provider_returns_placeholder_without_text_file(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "segment.wav"
    audio_path.write_bytes(b"fake")

    provider = load_callable_speech_to_text_provider(
        provider_name="local-dev",
        import_path="smhelper.infrastructure.asr.local_provider:transcribe",
    )

    result = provider.transcribe(SpeechToTextRequest(audio_path=audio_path))

    assert result.text == "Local ASR placeholder for segment.wav."
    assert result.provider_name == "local-dev"
    assert result.raw_response == '{"source":"placeholder","audio":"segment.wav"}'


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
