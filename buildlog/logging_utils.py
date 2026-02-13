"""stderr logger helpers for BuildLog."""

from __future__ import annotations

import sys
from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return an RFC3339 UTC timestamp with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class BuildLogLogger:
    """Simple structured logger writing to stderr only."""

    def _emit(self, level: str, message: str) -> None:
        print(f"[BUILDLOG {utc_timestamp()}] {level}: {message}", file=sys.stderr, flush=True)

    def info(self, message: str) -> None:
        self._emit("INFO", message)

    def warn(self, message: str) -> None:
        self._emit("WARN", message)

    def error(self, message: str) -> None:
        self._emit("ERROR", message)


LOGGER = BuildLogLogger()

