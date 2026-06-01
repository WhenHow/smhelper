"""Internal center API used by trusted worker nodes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
)

router = APIRouter(prefix="/api")


@router.get("/accounts/{platform}/{account_id}/storage-state")
def get_account_storage_state(
    *,
    request: Request,
    platform: str,
    account_id: str,
) -> FileResponse:
    """Return the stored browser storage-state file for a valid account."""
    with Session(request.app.state.engine) as session:
        auth_state = session.get(
            AccountAuthStateRecord,
            {"account_id": account_id, "platform": platform},
        )

    if auth_state is None or auth_state.status != "valid":
        raise HTTPException(status_code=404, detail="storage state not found")
    storage_state_path = Path(auth_state.storage_state_path)
    if not storage_state_path.exists():
        raise HTTPException(status_code=404, detail="storage state file not found")
    return FileResponse(storage_state_path, media_type="application/json")
