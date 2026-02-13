"""Custom errors for BuildLog."""


class BuildLogError(Exception):
    """Base BuildLog exception."""


class BuildLogConfigError(BuildLogError):
    """Raised when configuration is invalid or missing."""


class BuildLogSecretsError(BuildLogError):
    """Raised when secrets are missing or unreadable."""


class BuildLogStateError(BuildLogError):
    """Raised when state cannot be loaded or written."""


class BuildLogGitError(BuildLogError):
    """Raised when a git operation fails."""

