from __future__ import annotations

import pytest

from smhelper.workers.domain.rendezvous_hashing import (
    NoAvailableWorkerNode,
    RendezvousHashingNodeSelector,
)
from smhelper.workers.domain.worker_node import WorkerNode


def test_hrw_selects_the_same_available_node_for_the_same_account() -> None:
    selector = RendezvousHashingNodeSelector()
    nodes = [
        WorkerNode(
            id="node-a",
            queue_name="node.node-a.browser",
            supported_platforms=frozenset({"xhs"}),
            max_browser_sessions=10,
            active_browser_sessions=1,
        ),
        WorkerNode(
            id="node-b",
            queue_name="node.node-b.browser",
            supported_platforms=frozenset({"xhs"}),
            max_browser_sessions=10,
            active_browser_sessions=2,
        ),
        WorkerNode(
            id="node-c",
            queue_name="node.node-c.browser",
            supported_platforms=frozenset({"xhs"}),
            max_browser_sessions=10,
            active_browser_sessions=0,
        ),
    ]

    first = selector.select_node(account_id="account-1", nodes=nodes, platform="xhs")
    second = selector.select_node(
        account_id="account-1", nodes=list(reversed(nodes)), platform="xhs"
    )

    assert first == second
    assert first.id == "node-a"


def test_hrw_skips_offline_full_and_unsupported_nodes() -> None:
    selector = RendezvousHashingNodeSelector()
    nodes = [
        WorkerNode(
            id="node-a",
            queue_name="node.node-a.browser",
            supported_platforms=frozenset({"xhs"}),
            max_browser_sessions=10,
            active_browser_sessions=0,
            online=False,
        ),
        WorkerNode(
            id="node-b",
            queue_name="node.node-b.browser",
            supported_platforms=frozenset({"xhs"}),
            max_browser_sessions=2,
            active_browser_sessions=2,
        ),
        WorkerNode(
            id="node-c",
            queue_name="node.node-c.browser",
            supported_platforms=frozenset({"dy"}),
            max_browser_sessions=10,
            active_browser_sessions=0,
        ),
        WorkerNode(
            id="node-d",
            queue_name="node.node-d.browser",
            supported_platforms=frozenset({"xhs"}),
            max_browser_sessions=10,
            active_browser_sessions=0,
        ),
    ]

    selected = selector.select_node(account_id="account-1", nodes=nodes, platform="xhs")

    assert selected.id == "node-d"


def test_hrw_raises_when_no_worker_can_accept_the_account() -> None:
    selector = RendezvousHashingNodeSelector()

    with pytest.raises(NoAvailableWorkerNode):
        selector.select_node(account_id="account-1", nodes=[], platform="xhs")
