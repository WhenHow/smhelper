"""Account to worker-node binding rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountNodeBinding:
    """Allowed worker nodes for a platform account.

    An empty allowed-node set means the account can be placed on any online
    worker that supports the platform.
    """

    account_id: str
    allowed_node_ids: frozenset[str]

    def is_node_allowed(self, node_id: str) -> bool:
        """Return whether the account may run on the node."""
        return not self.allowed_node_ids or node_id in self.allowed_node_ids
