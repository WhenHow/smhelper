"""SQLAlchemy records for the live bounded context."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from smhelper.live.domain.account_live_session import ACTIVE_SESSION_STATUSES
from smhelper.infrastructure.persistence.sqlalchemy.base import Base


class LiveTaskRecord(Base):
    """Persisted live task state."""

    __tablename__ = "live_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    room_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(256))
    stream_url: Mapped[str | None] = mapped_column(Text)
    segment_time_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(512))


class CandidateQuestionRecord(Base):
    """Persisted LLM-generated question and operator review result."""

    __tablename__ = "candidate_questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    live_task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    final_text: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(512))


class AccountLiveSessionRecord(Base):
    """Persisted account browser session inside a live room."""

    __tablename__ = "account_live_sessions"
    __table_args__ = (
        UniqueConstraint(
            "active_slot_key",
            name="uq_account_live_sessions_active_slot_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    live_task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    room_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    active_slot_key: Mapped[str | None] = mapped_column(String(160))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(512))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restart_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @staticmethod
    def build_active_slot_key(
        *,
        live_task_id: str,
        account_id: str,
        status: str,
    ) -> str | None:
        """Return the unique slot key for active account/live-task sessions."""
        active_values = {
            session_status.value for session_status in ACTIVE_SESSION_STATUSES
        }
        if status in active_values:
            return f"{live_task_id}:{account_id}"
        return None


class DispatchJobRecord(Base):
    """Persisted request to send an approved question."""

    __tablename__ = "dispatch_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_question_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    live_task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_live_session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    final_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(512))


class SendAttemptRecord(Base):
    """Persisted audit row for a worker-side send attempt."""

    __tablename__ = "send_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dispatch_job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_live_session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    success_detection: Mapped[str] = mapped_column(String(64), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(String(512))
    page_snapshot_path: Mapped[str | None] = mapped_column(String(512))


class LiveSegmentRecord(Base):
    """Persisted media segment and processing artifacts."""

    __tablename__ = "live_segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    live_task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    video_path: Mapped[str] = mapped_column(String(512), nullable=False)
    first_frame_path: Mapped[str | None] = mapped_column(String(512))
    last_frame_path: Mapped[str | None] = mapped_column(String(512))
    audio_path: Mapped[str | None] = mapped_column(String(512))
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TranscriptRecord(Base):
    """Persisted ASR transcript for one completed live segment."""

    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    live_task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    transcribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(String(512))
