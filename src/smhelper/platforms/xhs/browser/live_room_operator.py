"""Xiaohongshu live-room browser operator for worker-node tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from smhelper.infrastructure.task_queue.celery.node_handler import BrowserActionResult


class XhsLiveRoomSession(Protocol):
    """One open Xiaohongshu live-room browser session."""

    def send_comment(self, text: str) -> None:
        """Send one comment from this already-open live-room page."""

    def close(self) -> None:
        """Close this live-room browser session."""


class XhsLiveRoomSessionManager(Protocol):
    """Factory that opens Xiaohongshu live-room browser sessions."""

    def open_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> XhsLiveRoomSession:
        """Open a live room using the account storage-state file."""


@dataclass(slots=True)
class XhsLiveRoomBrowserOperator:
    """Adapt Xiaohongshu browser sessions to worker-node browser tasks."""

    session_manager: XhsLiveRoomSessionManager
    _sessions: dict[str, XhsLiveRoomSession] = field(default_factory=dict)

    def enter_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> BrowserActionResult:
        """Open and remember one Xiaohongshu live-room session."""
        try:
            self._sessions[session_id] = self.session_manager.open_live_room(
                session_id=session_id,
                room_url=room_url,
                storage_state_path=storage_state_path,
            )
        except Exception as exc:
            return BrowserActionResult(success=False, failure_reason=str(exc))
        return BrowserActionResult(success=True)

    def send_comment(self, *, session_id: str, final_text: str) -> BrowserActionResult:
        """Send a comment through an existing Xiaohongshu live-room session."""
        live_session = self._sessions.get(session_id)
        if live_session is None:
            return _missing_session_result(session_id)

        try:
            live_session.send_comment(final_text)
        except Exception as exc:
            return BrowserActionResult(success=False, failure_reason=str(exc))
        return BrowserActionResult(success=True)

    def close_session(self, *, session_id: str) -> BrowserActionResult:
        """Close and forget an existing Xiaohongshu live-room session."""
        live_session = self._sessions.pop(session_id, None)
        if live_session is None:
            return _missing_session_result(session_id)

        try:
            live_session.close()
        except Exception as exc:
            return BrowserActionResult(success=False, failure_reason=str(exc))
        return BrowserActionResult(success=True)


def _missing_session_result(session_id: str) -> BrowserActionResult:
    return BrowserActionResult(
        success=False,
        failure_reason=f"live room session is not open: {session_id}",
    )
