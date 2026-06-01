"""SQLAlchemy records for the account bounded context."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from smhelper.infrastructure.persistence.sqlalchemy.base import Base


class PlatformAccountRecord(Base):
    """Persisted platform account metadata."""

    __tablename__ = "platform_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_send_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    sends_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountAuthStateRecord(Base):
    """Persisted browser storage-state metadata for an account."""

    __tablename__ = "account_auth_states"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_state_path: Mapped[str] = mapped_column(String(512), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(512))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
