from __future__ import annotations

from asyncio import run

import pytest
from fastapi.testclient import TestClient

from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.web.admin import AdminCredentials, SingleAdminAuth
from smhelper.web.app import create_app


def test_create_app_registers_sqladmin_route_and_model_views() -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")

    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )

    assert "/admin" in {route.path for route in app.routes}
    assert [view.__class__.__name__ for view in app.state.admin.views] == [
        "PlatformAccountAdmin",
        "AccountAuthStateAdmin",
        "WorkerNodeAdmin",
        "LiveTaskAdmin",
        "CandidateQuestionAdmin",
        "AccountLiveSessionAdmin",
        "DispatchJobAdmin",
        "SendAttemptAdmin",
    ]
    engine.dispose()


@pytest.mark.parametrize(
    ("username", "password", "expected_status"),
    [
        ("admin", "secret", 302),
        ("admin", "wrong", 400),
    ],
)
def test_single_admin_login_uses_configured_credentials(
    username: str,
    password: str,
    expected_status: int,
) -> None:
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )

    with TestClient(app, follow_redirects=False) as client:
        response = client.post(
            "/admin/login",
            data={"username": username, "password": password},
        )

    assert response.status_code == expected_status
    engine.dispose()


def test_single_admin_auth_backend_sets_and_clears_session() -> None:
    class FakeRequest:
        def __init__(self, form_data: dict[str, str]) -> None:
            self._form_data = form_data
            self.session: dict[str, str] = {}

        async def form(self) -> dict[str, str]:
            return self._form_data

    auth = SingleAdminAuth(
        AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        )
    )
    request = FakeRequest({"username": "admin", "password": "secret"})

    assert run(auth.login(request)) is True
    assert run(auth.authenticate(request)) is True
    assert run(auth.logout(request)) is True
    assert run(auth.authenticate(request)) is False
