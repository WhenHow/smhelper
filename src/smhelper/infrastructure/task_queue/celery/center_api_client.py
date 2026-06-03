"""HTTP client used by worker nodes to call the trusted center API."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TypeAlias
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from smhelper.core.exceptions import SmHelperError

JsonBodyValue: TypeAlias = str | int | list[str] | None


class CenterApiError(SmHelperError):
    """Raised when a worker node cannot call the center API."""


class HttpTransport(Protocol):
    """Minimal HTTP transport boundary for center API calls."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes:
        """Send one HTTP request and return the response body."""


@dataclass(frozen=True, slots=True)
class UrlLibHttpTransport:
    """Stdlib-backed HTTP transport.

    This keeps the first worker callback implementation dependency-free. The
    adapter boundary is intentionally small so it can be replaced by httpx if
    we later choose to add a production HTTP client dependency.
    """

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes:
        """Send one HTTP request through urllib."""
        request = Request(url=url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return response.read()
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise CenterApiError(
                f"center API {method} {url} failed with HTTP {exc.code}: {details}"
            ) from exc
        except URLError as exc:
            raise CenterApiError(
                f"center API {method} {url} failed: {exc.reason}"
            ) from exc


@dataclass(frozen=True, slots=True)
class HttpCenterApiClient:
    """HTTP implementation of the worker-side center API client protocol."""

    base_url: str
    storage_state_dir: Path
    transport: HttpTransport = field(default_factory=UrlLibHttpTransport)
    timeout_seconds: float = 15.0

    def fetch_storage_state(self, *, account_id: str, platform: str) -> Path:
        """Fetch an account storage-state JSON file and save it locally."""
        storage_state = self.transport.request(
            method="GET",
            url=(
                f"{self._base_url}/api/accounts/{_path_part(platform)}/"
                f"{_path_part(account_id)}/storage-state"
            ),
            headers={},
            body=None,
            timeout_seconds=self.timeout_seconds,
        )
        storage_state_path = (
            self.storage_state_dir
            / _path_part(platform)
            / _path_part(account_id)
            / "storage_state.json"
        )
        storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        storage_state_path.write_bytes(storage_state)
        return storage_state_path

    def report_session_status(
        self,
        *,
        session_id: str,
        status: str,
        failure_reason: str | None,
    ) -> None:
        """Report account live-session state to the center."""
        self.transport.request(
            method="POST",
            url=(f"{self._base_url}/api/live/sessions/{_path_part(session_id)}/status"),
            headers={"Content-Type": "application/json"},
            body=_json_body(
                {
                    "status": status,
                    "failure_reason": failure_reason,
                }
            ),
            timeout_seconds=self.timeout_seconds,
        )

    def report_send_result(
        self,
        *,
        dispatch_job_id: str,
        session_id: str,
        account_id: str,
        status: str,
        failure_reason: str | None,
    ) -> None:
        """Report one send dispatch result to the center."""
        self.transport.request(
            method="POST",
            url=f"{self._base_url}/api/live/send-results",
            headers={"Content-Type": "application/json"},
            body=_json_body(
                {
                    "dispatch_job_id": dispatch_job_id,
                    "session_id": session_id,
                    "account_id": account_id,
                    "status": status,
                    "failure_reason": failure_reason,
                }
            ),
            timeout_seconds=self.timeout_seconds,
        )

    def report_worker_heartbeat(
        self,
        *,
        node_id: str,
        queue_name: str,
        supported_platforms: list[str],
        max_browser_sessions: int,
        active_browser_sessions: int,
    ) -> None:
        """Report worker-node liveness and browser-capacity state to the center."""
        self.transport.request(
            method="POST",
            url=f"{self._base_url}/api/workers/{_path_part(node_id)}/heartbeat",
            headers={"Content-Type": "application/json"},
            body=_json_body(
                {
                    "queue_name": queue_name,
                    "supported_platforms": supported_platforms,
                    "max_browser_sessions": max_browser_sessions,
                    "active_browser_sessions": active_browser_sessions,
                }
            ),
            timeout_seconds=self.timeout_seconds,
        )

    @property
    def _base_url(self) -> str:
        return self.base_url.rstrip("/")


def _path_part(value: str) -> str:
    return quote(value, safe="")


def _json_body(payload: dict[str, JsonBodyValue]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
