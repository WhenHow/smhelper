"""Local development ASR provider callable.

This provider is intentionally deterministic and dependency-free. It is useful
for local smoke tests of the segment-processing pipeline when a real vendor ASR
account has not been configured yet.
"""

from __future__ import annotations

import json

from smhelper.live.application.ports.speech_to_text import (
    SpeechToTextRequest,
    TranscriptionResult,
)

LOCAL_PROVIDER_NAME = "local-dev"


def transcribe(request: SpeechToTextRequest) -> TranscriptionResult:
    """Return adjacent text-file content or a clear local placeholder."""
    transcript_path = request.audio_path.with_suffix(".txt")
    if transcript_path.exists():
        text = transcript_path.read_text(encoding="utf-8").strip()
        return TranscriptionResult(
            text=text,
            provider_name=LOCAL_PROVIDER_NAME,
            raw_response=_json_body(
                {
                    "source": "adjacent_text",
                    "path": str(transcript_path),
                }
            ),
        )
    return TranscriptionResult(
        text=f"Local ASR placeholder for {request.audio_path.name}.",
        provider_name=LOCAL_PROVIDER_NAME,
        raw_response=_json_body(
            {
                "source": "placeholder",
                "audio": request.audio_path.name,
            }
        ),
    )


def _json_body(payload: dict[str, str]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
