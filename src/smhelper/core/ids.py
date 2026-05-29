"""Identifier generation abstractions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import uuid4

from smhelper.core.exceptions import SmHelperError


class IdGenerationError(SmHelperError):
    """Raised when an ID generator cannot produce a new identifier."""


class IdGenerator(Protocol):
    """Produces identifiers for persisted application records."""

    def new_id(self, prefix: str) -> str:
        """Return a new identifier using the provided semantic prefix."""


class UuidGenerator:
    """UUID-backed identifier generator."""

    def new_id(self, prefix: str) -> str:
        """Return a prefixed UUID string."""
        return f"{prefix}-{uuid4().hex}"


class SequenceIdGenerator:
    """Deterministic identifier generator for tests and scripted runs."""

    def __init__(self, ids: Iterable[str]) -> None:
        self._ids = iter(ids)

    def new_id(self, prefix: str) -> str:
        """Return the next configured ID."""
        try:
            return next(self._ids)
        except StopIteration as exc:
            raise IdGenerationError(f"No IDs left for prefix {prefix!r}") from exc
