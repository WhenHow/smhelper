"""Worker-node browser task handler boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from smhelper.infrastructure.task_queue.celery.publisher import (
    CloseSessionPayload,
    EnterLiveRoomPayload,
    SendCommentPayload,
)


@dataclass(frozen=True, slots=True)
class BrowserActionResult:
    """Normalized result from a browser operation on a worker node."""

    success: bool
    failure_reason: str | None = None


class CenterApiClient(Protocol):
    """Client used by worker nodes to talk back to the center API."""

    def fetch_storage_state(self, *, account_id: str, platform: str) -> Path:
        """Fetch the storage-state file for an account."""

    def report_session_status(
        self,
        *,
        session_id: str,
        status: str,
        failure_reason: str | None,
    ) -> None:
        """Report account live session status to the center."""

    def report_send_result(
        self,
        *,
        dispatch_job_id: str,
        session_id: str,
        account_id: str,
        status: str,
        failure_reason: str | None,
    ) -> None:
        """Report send job result to the center."""

    def report_worker_heartbeat(
        self,
        *,
        node_id: str,
        queue_name: str,
        supported_platforms: list[str],
        max_browser_sessions: int,
        active_browser_sessions: int,
    ) -> None:
        """Report worker-node liveness and browser capacity to the center."""


class LiveRoomBrowserOperator(Protocol):
    """Browser operations a worker node must provide."""

    def enter_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> BrowserActionResult:
        """Open the live room and keep the account session waiting."""

    def send_comment(self, *, session_id: str, final_text: str) -> BrowserActionResult:
        """Send text in an existing live room session."""

    def close_session(self, *, session_id: str) -> BrowserActionResult:
        """Close an existing live room session."""


@dataclass(frozen=True, slots=True)
class NodeBrowserTaskHandler:
    """Coordinates worker-node browser operations and center callbacks."""

    center_api: CenterApiClient
    browser_operator: LiveRoomBrowserOperator

    def enter_live_room(self, payload: EnterLiveRoomPayload) -> None:
        """Fetch auth state, enter the live room and report the session status."""
        try:
            storage_state_path = self.center_api.fetch_storage_state(
                account_id=payload.account_id,
                platform=payload.platform,
            )
            result = self.browser_operator.enter_live_room(
                session_id=payload.session_id,
                room_url=payload.room_url,
                storage_state_path=storage_state_path,
            )
        except Exception as exc:  # noqa: BLE001 - local node failures must be reported.
            result = BrowserActionResult(
                success=False,
                failure_reason=_failure_reason(exc),
            )
        self.center_api.report_session_status(
            session_id=payload.session_id,
            status="waiting" if result.success else "failed",
            failure_reason=result.failure_reason,
        )

    def send_comment(self, payload: SendCommentPayload) -> None:
        """Send a comment and report first-phase operation result."""
        try:
            result = self.browser_operator.send_comment(
                session_id=payload.session_id,
                final_text=payload.final_text,
            )
        except Exception as exc:  # noqa: BLE001 - local node failures must be reported.
            result = BrowserActionResult(
                success=False,
                failure_reason=_failure_reason(exc),
            )
        self.center_api.report_send_result(
            dispatch_job_id=payload.dispatch_job_id,
            session_id=payload.session_id,
            account_id=payload.account_id,
            status="success" if result.success else "failed",
            failure_reason=result.failure_reason,
        )

    def close_session(self, payload: CloseSessionPayload) -> None:
        """Close a browser session and report terminal session state."""
        try:
            result = self.browser_operator.close_session(session_id=payload.session_id)
        except Exception as exc:  # noqa: BLE001 - local node failures must be reported.
            result = BrowserActionResult(
                success=False,
                failure_reason=_failure_reason(exc),
            )
        self.center_api.report_session_status(
            session_id=payload.session_id,
            status="closed" if result.success else "lost",
            failure_reason=result.failure_reason,
        )


def _failure_reason(exc: Exception) -> str:
    reason = str(exc).strip()
    if reason:
        return reason
    return exc.__class__.__name__
