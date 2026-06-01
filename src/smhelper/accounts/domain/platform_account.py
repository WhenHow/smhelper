"""Platform account domain model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from smhelper.accounts.domain.account_auth_state import AccountAuthState


@dataclass(frozen=True, slots=True)
class PlatformAccount:
    """Authorized account that can participate in platform operations."""

    id: str
    platform: str
    display_name: str
    enabled: bool
    daily_send_limit: int
    sends_today: int = 0
    cooldown_until: datetime | None = None

    def is_available(self, *, now: datetime, auth_state: AccountAuthState) -> bool:
        """Return whether the account can be scheduled for a live task."""
        if not self.enabled:
            return False
        if auth_state.account_id != self.id or auth_state.platform != self.platform:
            return False
        if not auth_state.is_usable:
            return False
        if self.cooldown_until is not None and self.cooldown_until > now:
            return False
        return self.sends_today < self.daily_send_limit

    def disable(self) -> PlatformAccount:
        """Return a disabled copy of the account."""
        return replace(self, enabled=False)
