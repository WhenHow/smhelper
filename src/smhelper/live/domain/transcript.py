"""Transcript domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TranscriptStatus(str, Enum):
    """Processing status of an ASR transcript."""

    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Transcript:
    """ASR transcript for one completed live segment."""

    id: str
    live_task_id: str
    segment_id: str
    text: str
    provider_name: str
    raw_response: str
    status: TranscriptStatus
    transcribed_at: datetime
    failure_reason: str | None = None
