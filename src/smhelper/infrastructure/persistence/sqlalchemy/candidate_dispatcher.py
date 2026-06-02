"""SQLAlchemy-backed candidate approval and dispatch orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smhelper.accounts.domain.account_auth_state import (
    AccountAuthState,
    AccountAuthStatus,
)
from smhelper.accounts.domain.platform_account import PlatformAccount
from smhelper.core.clock import Clock
from smhelper.core.ids import IdGenerator
from smhelper.infrastructure.persistence.sqlalchemy.accounts import (
    AccountAuthStateRecord,
    PlatformAccountRecord,
)
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
from smhelper.live.domain.candidate_question import (
    CandidateQuestion,
    CandidateQuestionStatus,
    InvalidCandidateQuestion,
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
    forbidden_terms: tuple[str, ...] = ()

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
                approved_candidate = self._approve_candidate(
                    candidate=candidate,
                    final_text=final_text,
                    reviewed_by=reviewed_by,
                    reviewed_at=now,
                )
                if approved_candidate is None:
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
                candidate.status = approved_candidate.status.value
                candidate.final_text = approved_candidate.final_text
                candidate.reviewed_by = approved_candidate.reviewed_by
                candidate.reviewed_at = approved_candidate.reviewed_at
                candidate.rejection_reason = approved_candidate.rejection_reason
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

    def _approve_candidate(
        self,
        *,
        candidate: CandidateQuestionRecord,
        final_text: str,
        reviewed_by: str,
        reviewed_at: datetime,
    ) -> CandidateQuestion | None:
        try:
            return self._to_candidate(candidate).approve(
                final_text=final_text,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at,
                forbidden_terms=self.forbidden_terms,
            )
        except InvalidCandidateQuestion:
            return None

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
        available_account_ids = self._load_available_account_ids(
            session=session,
            records=waiting_records,
            now=now,
        )
        domain_sessions = [
            self._to_domain(record)
            for record in waiting_records
            if record.account_id in available_account_ids
        ]
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
    def _load_available_account_ids(
        *,
        session: Session,
        records: Sequence[AccountLiveSessionRecord],
        now: datetime,
    ) -> set[str]:
        account_keys = {(record.account_id, record.platform) for record in records}
        if not account_keys:
            return set()

        account_ids = {account_id for account_id, _ in account_keys}
        platforms = {platform for _, platform in account_keys}
        account_records = {
            (record.id, record.platform): record
            for record in session.scalars(
                select(PlatformAccountRecord).where(
                    PlatformAccountRecord.id.in_(account_ids),
                    PlatformAccountRecord.platform.in_(platforms),
                )
            ).all()
        }
        auth_records = {
            (record.account_id, record.platform): record
            for record in session.scalars(
                select(AccountAuthStateRecord).where(
                    AccountAuthStateRecord.account_id.in_(account_ids),
                    AccountAuthStateRecord.platform.in_(platforms),
                )
            ).all()
        }

        available: set[str] = set()
        for account_id, platform in account_keys:
            account_record = account_records.get((account_id, platform))
            auth_record = auth_records.get((account_id, platform))
            if account_record is None or auth_record is None:
                continue
            account = SqlAlchemyCandidateDispatcher._to_account(account_record)
            auth_state = SqlAlchemyCandidateDispatcher._to_auth_state(auth_record)
            if account.is_available(now=now, auth_state=auth_state):
                available.add(account_id)
        return available

    @staticmethod
    def _to_account(record: PlatformAccountRecord) -> PlatformAccount:
        return PlatformAccount(
            id=record.id,
            platform=record.platform,
            display_name=record.display_name,
            enabled=record.enabled,
            daily_send_limit=record.daily_send_limit,
            sends_today=record.sends_today,
            cooldown_until=record.cooldown_until,
        )

    @staticmethod
    def _to_auth_state(record: AccountAuthStateRecord) -> AccountAuthState:
        return AccountAuthState(
            account_id=record.account_id,
            platform=record.platform,
            status=AccountAuthStatus(record.status),
            storage_state_path=record.storage_state_path,
            failure_reason=record.failure_reason,
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

    @staticmethod
    def _to_candidate(record: CandidateQuestionRecord) -> CandidateQuestion:
        return CandidateQuestion(
            id=record.id,
            live_task_id=record.live_task_id,
            segment_id=record.segment_id,
            question=record.question,
            reason=record.reason,
            risk_level=record.risk_level,
            raw_response=record.raw_response,
            status=CandidateQuestionStatus(record.status),
            generated_at=record.generated_at,
            final_text=record.final_text,
            reviewed_by=record.reviewed_by,
            reviewed_at=record.reviewed_at,
            rejection_reason=record.rejection_reason,
        )
