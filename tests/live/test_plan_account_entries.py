from __future__ import annotations

from datetime import UTC, datetime
from random import Random

from smhelper.accounts.domain.account_auth_state import (
    AccountAuthState,
    AccountAuthStatus,
)
from smhelper.accounts.domain.account_node_binding import AccountNodeBinding
from smhelper.accounts.domain.platform_account import PlatformAccount
from smhelper.core.ids import SequenceIdGenerator
from smhelper.live.application.use_cases.plan_account_entries import (
    AccountEntryCandidate,
    PlanAccountEntriesUseCase,
)
from smhelper.live.domain.account_live_session import (
    AccountLiveSession,
    AccountLiveSessionStatus,
)
from smhelper.workers.domain.rendezvous_hashing import RendezvousHashingNodeSelector
from smhelper.workers.domain.worker_node import WorkerNode


def _candidate(account_id: str) -> AccountEntryCandidate:
    return AccountEntryCandidate(
        account=PlatformAccount(
            id=account_id,
            platform="xhs",
            display_name=account_id,
            enabled=True,
            daily_send_limit=10,
            sends_today=0,
        ),
        auth_state=AccountAuthState(
            account_id=account_id,
            platform="xhs",
            status=AccountAuthStatus.VALID,
            storage_state_path=f"data/auth/xhs/{account_id}/storage_state.json",
        ),
        node_binding=AccountNodeBinding(
            account_id=account_id, allowed_node_ids=frozenset()
        ),
    )


def _node(node_id: str) -> WorkerNode:
    return WorkerNode(
        id=node_id,
        queue_name=f"node.{node_id}.browser",
        supported_platforms=frozenset({"xhs"}),
        max_browser_sessions=10,
        active_browser_sessions=0,
    )


def test_plan_account_entries_assigns_all_available_accounts_with_stagger() -> None:
    plans = PlanAccountEntriesUseCase(
        selector=RendezvousHashingNodeSelector(),
        ids=SequenceIdGenerator(["session-1", "session-2"]),
        rng=Random(3),
    ).plan(
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        candidates=[_candidate("account-1"), _candidate("account-2")],
        nodes=[_node("node-a"), _node("node-b")],
        existing_sessions=[],
        now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert [plan.session.id for plan in plans] == ["session-1", "session-2"]
    assert {plan.session.account_id for plan in plans} == {"account-1", "account-2"}
    assert plans[0].delay_seconds in range(15, 46)
    assert plans[1].delay_seconds > plans[0].delay_seconds
    assert plans[1].delay_seconds - plans[0].delay_seconds in range(15, 46)
    assert {plan.queue_name for plan in plans} <= {
        "node.node-a.browser",
        "node.node-b.browser",
    }


def test_plan_account_entries_skips_accounts_with_active_session() -> None:
    existing = AccountLiveSession(
        id="existing-session",
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        account_id="account-1",
        node_id="node-a",
        status=AccountLiveSessionStatus.WAITING,
    )

    plans = PlanAccountEntriesUseCase(
        selector=RendezvousHashingNodeSelector(),
        ids=SequenceIdGenerator(["session-2"]),
        rng=Random(3),
    ).plan(
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        candidates=[_candidate("account-1"), _candidate("account-2")],
        nodes=[_node("node-a"), _node("node-b")],
        existing_sessions=[existing],
        now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert [plan.session.account_id for plan in plans] == ["account-2"]


def test_plan_account_entries_honors_account_node_binding() -> None:
    candidate = AccountEntryCandidate(
        account=_candidate("account-1").account,
        auth_state=_candidate("account-1").auth_state,
        node_binding=AccountNodeBinding(
            account_id="account-1",
            allowed_node_ids=frozenset({"node-b"}),
        ),
    )

    plans = PlanAccountEntriesUseCase(
        selector=RendezvousHashingNodeSelector(),
        ids=SequenceIdGenerator(["session-1"]),
        rng=Random(3),
    ).plan(
        live_task_id="live-1",
        platform="xhs",
        room_url="https://example.com/live/1",
        candidates=[candidate],
        nodes=[_node("node-a"), _node("node-b")],
        existing_sessions=[],
        now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert plans[0].session.node_id == "node-b"
    assert plans[0].queue_name == "node.node-b.browser"
