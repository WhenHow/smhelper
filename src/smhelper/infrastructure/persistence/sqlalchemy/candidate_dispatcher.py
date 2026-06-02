"""SQLAlchemy-backed candidate approval and dispatch orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.core.clock import Clock
from smhelper.core.ids import IdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
    CandidateQuestionRecord,
    DispatchJobRecord,
    LiveTaskRecord,
)
from smhelper.infrastructure.persistence.sqlalchemy.workers import WorkerNodeRecord
from smhelper.infrastructure.task_queue.celery.publisher import SendCommentPayload
from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.live.domain.policies.send_account_policy import (
    NoWaitingSessionAvailable,
    SendAccountPolicy,
)


class SendCommentTaskPublisher(Protocol):
    """Publisher capable of sending approved comments to browser-node queues."""

    def send_comment(self, *, queue_name: str, payload: SendCommentPayload) -> None:
        """Publish one send-comment task."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyCandidateDispatcher:
    """Approve candidates, create dispatch jobs and publish send tasks."""

    session_factory: sessionmaker[Session]
    ids: IdGenerator
    clock: Clock
    send_account_policy: SendAccountPolicy
    browser_task_publisher: SendCommentTaskPublisher

    def approve_and_dispatch(
        self,
        *,
        candidate_ids: list[str],
        reviewed_by: str,
    ) -> list[str]:
        """Approve candidates with final text and dispatch them to waiting sessions."""
        now = self.clock.now()
        published_jobs: list[tuple[str, SendCommentPayload]] = []
        dispatched_job_ids: list[str] = []

        with self.session_factory() as session:
            candidates = session.scalars(
                select(CandidateQuestionRecord).where(
                    CandidateQuestionRecord.id.in_(candidate_ids)
                )
            ).all()
            running_live_task_ids = self._load_running_live_task_ids(
                session=session,
                live_task_ids={candidate.live_task_id for candidate in candidates},
            )
            for candidate in candidates:
                if candidate.status != "pending_review":
                    continue
                if candidate.live_task_id not in running_live_task_ids:
                    continue
                final_text = (candidate.final_text or "").strip()
                if not final_text:
                    continue

                selected_session = self._select_waiting_session(
                    session=session,
                    live_task_id=candidate.live_task_id,
                    now=now,
                )
                if selected_session is None:
                    continue

                worker = session.get(WorkerNodeRecord, selected_session.node_id)
                if worker is None:
                    continue

                dispatch_job_id = self.ids.new_id("job")
                candidate.status = "approved"
                candidate.reviewed_by = reviewed_by
                candidate.reviewed_at = now
                selected_session.status = "sending"
                selected_session.send_started_at = now
                session.add(
                    DispatchJobRecord(
                        id=dispatch_job_id,
                        candidate_question_id=candidate.id,
                        live_task_id=candidate.live_task_id,
                        account_live_session_id=selected_session.id,
                        account_id=selected_session.account_id,
                        final_text=final_text,
                        status="pending",
                        created_at=now,
                    )
                )
                published_jobs.append(
                    (
                        worker.queue_name,
                        SendCommentPayload(
                            dispatch_job_id=dispatch_job_id,
                            session_id=selected_session.id,
                            account_id=selected_session.account_id,
                            final_text=final_text,
                        ),
                    )
                )
                dispatched_job_ids.append(dispatch_job_id)

            session.commit()

        for queue_name, payload in published_jobs:
            self.browser_task_publisher.send_comment(
                queue_name=queue_name,
                payload=payload,
            )
        return dispatched_job_ids

    @staticmethod
    def _load_running_live_task_ids(
        *,
        session: Session,
        live_task_ids: set[str],
    ) -> set[str]:
        if not live_task_ids:
            return set()
        records = session.scalars(
            select(LiveTaskRecord.id).where(
                LiveTaskRecord.id.in_(live_task_ids),
                LiveTaskRecord.status == "running",
            )
        ).all()
        return set(records)

    def _select_waiting_session(
        self,
        *,
        session: Session,
        live_task_id: str,
        now: datetime,
    ) -> AccountLiveSessionRecord | None:
        waiting_records = session.scalars(
            select(AccountLiveSessionRecord).where(
                AccountLiveSessionRecord.live_task_id == live_task_id,
                AccountLiveSessionRecord.status == "waiting",
            )
        ).all()
        domain_sessions = [self._to_domain(record) for record in waiting_records]
        try:
            selected = self.send_account_policy.select_session(
                sessions=domain_sessions,
                now=now,
            )
        except NoWaitingSessionAvailable:
            return None
        return next(
            (record for record in waiting_records if record.id == selected.id),
            None,
        )

    @staticmethod
    def _to_domain(record: AccountLiveSessionRecord) -> AccountLiveSession:
        return AccountLiveSession(
            id=record.id,
            live_task_id=record.live_task_id,
            platform=record.platform,
            room_url=record.room_url,
            account_id=record.account_id,
            node_id=record.node_id,
            status=AccountLiveSessionStatus(record.status),
            opened_at=record.opened_at,
            last_heartbeat_at=record.last_heartbeat_at,
            last_send_at=record.last_send_at,
            failure_reason=record.failure_reason,
            closed_at=record.closed_at,
            restart_count=record.restart_count,
            cooldown_until=record.cooldown_until,
            send_started_at=record.send_started_at,
        )
