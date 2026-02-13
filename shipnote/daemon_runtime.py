"""Daemon runtime status persistence helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state_manager import utc_now

DAEMON_STATUS_FILE = "daemon.json"


def daemon_status_path(shipnote_dir: Path) -> Path:
    """Return daemon status path for repo."""
    return shipnote_dir / DAEMON_STATUS_FILE


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def write_daemon_status(shipnote_dir: Path, *, config_path: str) -> None:
    """Persist daemon runtime metadata."""
    path = daemon_status_path(shipnote_dir)
    payload = {
        "pid": os.getpid(),
        "started_at": utc_now(),
        "config_path": config_path,
    }
    _atomic_write(path, payload)


def clear_daemon_status(shipnote_dir: Path) -> None:
    """Remove daemon runtime metadata."""
    path = daemon_status_path(shipnote_dir)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def read_daemon_status(shipnote_dir: Path) -> dict[str, Any] | None:
    """Load daemon runtime metadata if available."""
    path = daemon_status_path(shipnote_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def is_pid_alive(pid: int) -> bool:
    """Check if a PID appears alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def uptime_seconds(started_at: str) -> int | None:
    """Return daemon uptime seconds from RFC3339 timestamp."""
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt.astimezone(timezone.utc)
    return max(0, int(delta.total_seconds()))

