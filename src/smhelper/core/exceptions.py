"""Base exceptions shared across smhelper contexts."""


class SmHelperError(Exception):
    """Base class for expected smhelper errors."""


class ConfigurationError(SmHelperError):
    """Raised when runtime configuration is invalid."""
