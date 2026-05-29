"""Clock abstractions used to keep time-dependent logic testable."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Provides the current time for application services."""

    def now(self) -> datetime:
        """Return the current timezone-aware datetime."""


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Clock implementation that always returns the configured time."""

    value: datetime

    def now(self) -> datetime:
        """Return the fixed datetime."""
        return self.value


class SystemClock:
    """Clock implementation backed by the system UTC time."""

    def now(self) -> datetime:
        """Return the current UTC datetime."""
        return datetime.now(tz=UTC)
