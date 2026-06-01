from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.session import (
    create_engine_from_url,
)
from smhelper.web.admin import AdminCredentials
from smhelper.web.app import create_app


def test_storage_state_api_serves_valid_account_storage_state(tmp_path: Path) -> None:
    database_path = tmp_path / "smhelper.db"
    storage_state_path = tmp_path / "storage_state.json"
    storage_state_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )
    with Session(engine) as session:
        session.add(
            AccountAuthStateRecord(
                account_id="account-1",
                platform="xhs",
                status="valid",
                storage_state_path=str(storage_state_path),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/api/accounts/xhs/account-1/storage-state")

    assert response.status_code == 200
    assert response.json() == {"cookies": [], "origins": []}
    engine.dispose()


def test_storage_state_api_returns_404_for_expired_auth_state(tmp_path: Path) -> None:
    database_path = tmp_path / "smhelper.db"
    engine = create_engine_from_url(f"sqlite+pysqlite:///{database_path}")
    app = create_app(
        engine=engine,
        admin_credentials=AdminCredentials(
            username="admin",
            password="secret",
            secret_key="test-secret",
        ),
    )
    with Session(engine) as session:
        session.add(
            AccountAuthStateRecord(
                account_id="account-1",
                platform="xhs",
                status="expired",
                storage_state_path=str(tmp_path / "missing.json"),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/api/accounts/xhs/account-1/storage-state")

    assert response.status_code == 404
    engine.dispose()
