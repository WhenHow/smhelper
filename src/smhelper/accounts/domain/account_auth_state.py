"""Platform account authentication state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class AccountAuthStatus(str, Enum):
    """Authentication state for a platform account."""

    VALID = "valid"
    EXPIRED = "expired"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class AccountAuthState:
    """Metadata for a stored browser login state."""

    account_id: str
    platform: str
    status: AccountAuthStatus
    storage_state_path: str
    failure_reason: str | None = None

    @property
    def is_usable(self) -> bool:
        """Return whether this auth state can be loaded by a worker node."""
        return self.status is AccountAuthStatus.VALID and bool(
            self.storage_state_path.strip()
        )

    def mark_expired(self, *, reason: str) -> AccountAuthState:
        """Return a copy marked as expired."""
        return replace(
            self,
            status=AccountAuthStatus.EXPIRED,
            failure_reason=reason,
        )
