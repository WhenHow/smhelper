"""Port for observing live-room status and stream URLs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class LiveStreamObservationStatus(str, Enum):
    """Live-room status observed by a center-side anonymous observer."""

    LIVE = "live"
    NOT_LIVE = "not_live"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LiveStreamObservation:
    """Observed live-room status and optional stream URL."""

    status: LiveStreamObservationStatus
    stream_url: str | None = None


class LiveStreamObserver(Protocol):
    """Observes a live-room page and extracts a stream URL when available."""

    def observe(self, *, room_url: str) -> LiveStreamObservation:
        """Observe the live room once."""


class LiveStreamObservationSession(Protocol):
    """Long-lived observer page for one live room."""

    def observe(self) -> LiveStreamObservation:
        """Observe the already-open live room page once."""

    def wait(self, timeout_ms: int) -> None:
        """Wait before the next observation without closing the page."""

    def close(self) -> None:
        """Close the observer page and its browser context."""


class LiveStreamObservationSessionFactory(Protocol):
    """Creates long-lived observer sessions for live rooms."""

    def open_session(self, *, room_url: str) -> LiveStreamObservationSession:
        """Open one observer session for the live room."""
