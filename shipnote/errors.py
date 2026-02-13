"""Custom errors for Shipnote."""


class ShipnoteError(Exception):
    """Base Shipnote exception."""


class ShipnoteConfigError(ShipnoteError):
    """Raised when configuration is invalid or missing."""


class ShipnoteSecretsError(ShipnoteError):
    """Raised when secrets are missing or unreadable."""


class ShipnoteStateError(ShipnoteError):
    """Raised when state cannot be loaded or written."""


class ShipnoteGitError(ShipnoteError):
    """Raised when a git operation fails."""

