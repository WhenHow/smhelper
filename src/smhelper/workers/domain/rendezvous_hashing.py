"""Rendezvous hashing based worker node selection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

from smhelper.core.exceptions import SmHelperError
from smhelper.workers.domain.worker_node import WorkerNode


class NoAvailableWorkerNode(SmHelperError):
    """Raised when no worker node can accept a browser session."""


@dataclass(frozen=True, slots=True)
class RendezvousHashingNodeSelector:
    """Select worker nodes with HRW/Rendezvous hashing.

    HRW keeps the same account mapped to the same node while the node set is
    stable, and only remaps a subset of accounts when nodes are added or
    removed.
    """

    def select_node(
        self,
        *,
        account_id: str,
        nodes: Iterable[WorkerNode],
        platform: str,
    ) -> WorkerNode:
        """Return the highest-scoring available node for the account."""
        ranked_nodes = sorted(
            (node for node in nodes if node.can_accept(platform)),
            key=lambda node: self._score(account_id=account_id, node_id=node.id),
            reverse=True,
        )
        if not ranked_nodes:
            raise NoAvailableWorkerNode(
                f"No available worker node for account {account_id!r} on {platform!r}"
            )
        return ranked_nodes[0]

    @staticmethod
    def _score(*, account_id: str, node_id: str) -> int:
        digest = sha256(f"{node_id}:{account_id}".encode("utf-8")).digest()
        return int.from_bytes(digest, byteorder="big")
