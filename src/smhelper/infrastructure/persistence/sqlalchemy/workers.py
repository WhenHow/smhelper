"""SQLAlchemy records for worker nodes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from smhelper.infrastructure.persistence.sqlalchemy.base import Base


class WorkerNodeRecord(Base):
    """Persisted remote worker node configuration and runtime status."""

    __tablename__ = "worker_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    queue_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    supported_platforms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    max_browser_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    active_browser_sessions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
