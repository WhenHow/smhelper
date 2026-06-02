from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from smhelper.infrastructure.task_queue.celery.center_api_client import (
    HttpCenterApiClient,
)


@dataclass
class FakeHttpTransport:
    responses: list[bytes]
    requests: list[tuple[str, str, dict[str, str], bytes | None, float]] = field(
        default_factory=list
    )

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes:
        self.requests.append((method, url, headers, body, timeout_seconds))
        return self.responses.pop(0)


def test_http_center_api_client_fetches_storage_state_to_local_file(
    tmp_path: Path,
) -> None:
    transport = FakeHttpTransport(responses=[b'{"cookies":[],"origins":[]}'])
    client = HttpCenterApiClient(
        base_url="https://center.example/",
        storage_state_dir=tmp_path,
        transport=transport,
        timeout_seconds=3.0,
    )

    storage_state_path = client.fetch_storage_state(
        account_id="account 1",
        platform="xhs",
    )

    assert storage_state_path == tmp_path / "xhs" / "account%201" / "storage_state.json"
    assert storage_state_path.read_text(encoding="utf-8") == (
        '{"cookies":[],"origins":[]}'
    )
    assert transport.requests == [
        (
            "GET",
            "https://center.example/api/accounts/xhs/account%201/storage-state",
            {},
            None,
            3.0,
        )
    ]


def test_http_center_api_client_reports_session_status() -> None:
    transport = FakeHttpTransport(responses=[b'{"status":"ok"}'])
    client = HttpCenterApiClient(
        base_url="https://center.example",
        storage_state_dir=Path("storage-states"),
        transport=transport,
    )

    client.report_session_status(
        session_id="session-1",
        status="failed",
        failure_reason="browser_crashed",
    )

    assert transport.requests == [
        (
            "POST",
            "https://center.example/api/live/sessions/session-1/status",
            {"Content-Type": "application/json"},
            b'{"status":"failed","failure_reason":"browser_crashed"}',
            15.0,
        )
    ]


def test_http_center_api_client_reports_send_result() -> None:
    transport = FakeHttpTransport(responses=[b'{"status":"ok"}'])
    client = HttpCenterApiClient(
        base_url="https://center.example",
        storage_state_dir=Path("storage-states"),
        transport=transport,
    )

    client.report_send_result(
        dispatch_job_id="job-1",
        session_id="session-1",
        account_id="account-1",
        status="success",
        failure_reason=None,
    )

    assert transport.requests == [
        (
            "POST",
            "https://center.example/api/live/send-results",
            {"Content-Type": "application/json"},
            (
                b'{"dispatch_job_id":"job-1","session_id":"session-1",'
                b'"account_id":"account-1","status":"success",'
                b'"failure_reason":null}'
            ),
            15.0,
        )
    ]
