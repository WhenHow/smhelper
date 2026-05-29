"""Application-level exceptions for live assistant use cases."""

from smhelper.core.exceptions import SmHelperError


class ApplicationError(SmHelperError):
    """Base class for expected application use-case errors."""


class EntityNotFound(ApplicationError):
    """Raised when an application use case cannot find a required entity."""
