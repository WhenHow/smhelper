"""Domain exceptions for live assistant rules."""

from smhelper.core.exceptions import SmHelperError


class DomainError(SmHelperError):
    """Base class for live assistant domain rule violations."""


class AccountNotAvailable(DomainError):
    """Raised when an account cannot be scheduled into a live room."""


class PlatformMismatch(DomainError):
    """Raised when account and live room platforms are incompatible."""


class InvalidLiveRoom(DomainError):
    """Raised when a live room value is invalid."""


class InvalidCommentMessage(DomainError):
    """Raised when a comment message violates domain constraints."""


class SessionNotReady(DomainError):
    """Raised when a session is not ready to send comments."""
