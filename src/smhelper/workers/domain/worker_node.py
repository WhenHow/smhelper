"""Worker node domain model."""

from __future__ import annotations

from dataclasses import dataclass

from smhelper.core.exceptions import SmHelperError


class InvalidWorkerNode(SmHelperError):
    """Raised when a worker node definition is invalid."""


@dataclass(frozen=True, slots=True)
class WorkerNode:
    """Remote node that can run browser automation tasks for selected platforms."""

    id: str
    queue_name: str
    supported_platforms: frozenset[str]
    max_browser_sessions: int
    active_browser_sessions: int = 0
    online: bool = True

    def __post_init__(self) -> None:
        """Validate capacity and routing fields."""
        if not self.id.strip():
            raise InvalidWorkerNode("worker node id must not be blank")
        if not self.queue_name.strip():
            raise InvalidWorkerNode("worker node queue name must not be blank")
        if self.max_browser_sessions < 0:
            raise InvalidWorkerNode("max browser sessions must not be negative")
        if self.active_browser_sessions < 0:
            raise InvalidWorkerNode("active browser sessions must not be negative")
        if self.active_browser_sessions > self.max_browser_sessions:
            raise InvalidWorkerNode(
                "active browser sessions cannot exceed max sessions"
            )

    @property
    def available_browser_slots(self) -> int:
        """Return remaining browser session capacity."""
        return self.max_browser_sessions - self.active_browser_sessions

    def can_accept(self, platform: str) -> bool:
        """Return whether this node can accept a new browser session."""
        return (
            self.online
            and platform in self.supported_platforms
            and self.available_browser_slots > 0
        )
