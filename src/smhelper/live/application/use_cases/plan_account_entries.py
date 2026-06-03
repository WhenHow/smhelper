"""Plan staggered account entry tasks for a live task."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from random import Random

from smhelper.accounts.domain.account_auth_state import AccountAuthState
from smhelper.accounts.domain.account_node_binding import AccountNodeBinding
from smhelper.accounts.domain.platform_account import PlatformAccount
from smhelper.core.ids import IdGenerator
from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.workers.domain.rendezvous_hashing import (
    NoAvailableWorkerNode,
    RendezvousHashingNodeSelector,
)
from smhelper.workers.domain.worker_node import WorkerNode


@dataclass(frozen=True, slots=True)
class AccountEntryCandidate:
    """Account data needed to decide whether it should enter a live room."""

    account: PlatformAccount
    auth_state: AccountAuthState
    node_binding: AccountNodeBinding


@dataclass(frozen=True, slots=True)
class AccountEntryPlan:
    """Planned node task for one account live-room session."""

    session: AccountLiveSession
    queue_name: str
    delay_seconds: int


@dataclass(slots=True)
class PlanAccountEntriesUseCase:
    """Create staggered entry plans for all available accounts."""

    selector: RendezvousHashingNodeSelector
    ids: IdGenerator
    rng: Random
    min_interval_seconds: int = 15
    max_interval_seconds: int = 45

    def plan(
        self,
        *,
        live_task_id: str,
        platform: str,
        room_url: str,
        candidates: list[AccountEntryCandidate],
        nodes: list[WorkerNode],
        existing_sessions: list[AccountLiveSession],
        now: datetime,
    ) -> list[AccountEntryPlan]:
        """Return entry plans without creating duplicate active sessions."""
        shuffled_candidates = list(candidates)
        self.rng.shuffle(shuffled_candidates)
        planned: list[AccountEntryPlan] = []
        capacity_nodes = list(nodes)
        cumulative_delay = 0

        for candidate in shuffled_candidates:
            if not candidate.account.is_available(
                now=now, auth_state=candidate.auth_state
            ):
                continue
            if self._has_active_session(
                live_task_id=live_task_id,
                account_id=candidate.account.id,
                sessions=existing_sessions,
            ):
                continue

            allowed_nodes = [
                node
                for node in capacity_nodes
                if candidate.node_binding.is_node_allowed(node.id)
            ]
            try:
                selected_node = self.selector.select_node(
                    account_id=candidate.account.id,
                    nodes=allowed_nodes,
                    platform=platform,
                )
            except NoAvailableWorkerNode:
                continue

            cumulative_delay += self.rng.randint(
                self.min_interval_seconds,
                self.max_interval_seconds,
            )
            planned.append(
                AccountEntryPlan(
                    session=AccountLiveSession(
                        id=self.ids.new_id("session"),
                        live_task_id=live_task_id,
                        platform=platform,
                        room_url=room_url,
                        account_id=candidate.account.id,
                        node_id=selected_node.id,
                        status=AccountLiveSessionStatus.PLANNED,
                    ),
                    queue_name=selected_node.queue_name,
                    delay_seconds=cumulative_delay,
                )
            )
            capacity_nodes = self._reserve_node_slot(
                nodes=capacity_nodes,
                node_id=selected_node.id,
            )

        return planned

    @staticmethod
    def _has_active_session(
        *,
        live_task_id: str,
        account_id: str,
        sessions: list[AccountLiveSession],
    ) -> bool:
        return any(
            session.live_task_id == live_task_id
            and session.account_id == account_id
            and session.is_active
            for session in sessions
        )

    @staticmethod
    def _reserve_node_slot(
        *,
        nodes: list[WorkerNode],
        node_id: str,
    ) -> list[WorkerNode]:
        return [
            replace(
                node,
                active_browser_sessions=node.active_browser_sessions + 1,
            )
            if node.id == node_id
            else node
            for node in nodes
        ]
