"""SQLAlchemy-backed account entry dispatch orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from smhelper.infrastructure.persistence.sqlalchemy.live import (
    AccountLiveSessionRecord,
)
from smhelper.infrastructure.task_queue.celery.publisher import EnterLiveRoomPayload
from smhelper.live.application.use_cases.plan_account_entries import AccountEntryPlan


class EnterLiveRoomTaskPublisher(Protocol):
    """Publisher capable of asking browser nodes to enter a live room."""

    def enter_live_room(
        self,
        *,
        queue_name: str,
        payload: EnterLiveRoomPayload,
        countdown_seconds: int,
    ) -> None:
        """Publish one delayed enter-live-room task."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyAccountEntryDispatcher:
    """Persist planned account sessions and publish delayed entry tasks."""

    session_factory: sessionmaker[Session]
    browser_task_publisher: EnterLiveRoomTaskPublisher

    def dispatch(self, plans: list[AccountEntryPlan]) -> list[str]:
        """Persist entry plans before publishing browser-node tasks."""
        published_entries: list[tuple[str, EnterLiveRoomPayload, int]] = []
        session_ids: list[str] = []

        with self.session_factory() as session:
            for plan in plans:
                live_session = plan.session
                session.add(
                    AccountLiveSessionRecord(
                        id=live_session.id,
                        live_task_id=live_session.live_task_id,
                        platform=live_session.platform,
                        room_url=live_session.room_url,
                        account_id=live_session.account_id,
                        node_id=live_session.node_id,
                        status=live_session.status.value,
                        active_slot_key=AccountLiveSessionRecord.build_active_slot_key(
                            live_task_id=live_session.live_task_id,
                            account_id=live_session.account_id,
                            status=live_session.status.value,
                        ),
                        opened_at=live_session.opened_at,
                        last_heartbeat_at=live_session.last_heartbeat_at,
                        last_send_at=live_session.last_send_at,
                        failure_reason=live_session.failure_reason,
                        closed_at=live_session.closed_at,
                        restart_count=live_session.restart_count,
                        cooldown_until=live_session.cooldown_until,
                        send_started_at=live_session.send_started_at,
                    )
                )
                published_entries.append(
                    (
                        plan.queue_name,
                        EnterLiveRoomPayload(
                            session_id=live_session.id,
                            account_id=live_session.account_id,
                            live_task_id=live_session.live_task_id,
                            room_url=live_session.room_url,
                            platform=live_session.platform,
                        ),
                        plan.delay_seconds,
                    )
                )
                session_ids.append(live_session.id)

            session.commit()

        for queue_name, payload, countdown_seconds in published_entries:
            self.browser_task_publisher.enter_live_room(
                queue_name=queue_name,
                payload=payload,
                countdown_seconds=countdown_seconds,
            )
        return session_ids
