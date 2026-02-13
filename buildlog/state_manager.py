"""State load/save helpers for BuildLog."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import BuildLogStateError

MAX_PROCESSED_COMMITS = 100
MAX_RECENT_DRAFTS = 30


def utc_now() -> str:
    """Return an RFC3339 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def current_week_start(today: date | None = None) -> str:
    """Return Monday date (ISO) for the current UTC week."""
    d = today or datetime.now(timezone.utc).date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def default_state(last_commit_sha: str | None = None) -> dict[str, Any]:
    """Return a default state object."""
    return {
        "last_commit_sha": last_commit_sha,
        "queue_counter": 0,
        "last_run_timestamp": utc_now(),
        "processed_commits": [],
        "content_ledger": {
            "recent_drafts": [],
            "category_counts_this_week": {
                "authority": 0,
                "translation": 0,
                "personal": 0,
                "growth": 0,
            },
            "saveable_this_week": 0,
            "week_start": current_week_start(),
        },
    }


def state_path(buildlog_dir: Path) -> Path:
    """Return state file path for a repo."""
    return buildlog_dir / "state.json"


def _normalize_state(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    merged = default_state(last_commit_sha=data.get("last_commit_sha"))
    try:
        merged["queue_counter"] = max(0, int(data.get("queue_counter", 0)))
    except (TypeError, ValueError):
        merged["queue_counter"] = 0
    merged["last_run_timestamp"] = str(data.get("last_run_timestamp", merged["last_run_timestamp"]))

    processed = data.get("processed_commits", [])
    if not isinstance(processed, list):
        processed = []
    deduped: list[str] = []
    seen: set[str] = set()
    for item in [str(x) for x in processed]:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    merged["processed_commits"] = deduped[-MAX_PROCESSED_COMMITS:]

    ledger = data.get("content_ledger", {})
    if not isinstance(ledger, dict):
        ledger = {}

    merged_ledger = deepcopy(merged["content_ledger"])
    recent = ledger.get("recent_drafts", [])
    if isinstance(recent, list):
        merged_ledger["recent_drafts"] = recent[-MAX_RECENT_DRAFTS:]

    counts = ledger.get("category_counts_this_week", {})
    if isinstance(counts, dict):
        for key in ("authority", "translation", "personal", "growth"):
            try:
                merged_ledger["category_counts_this_week"][key] = int(counts.get(key, 0))
            except (TypeError, ValueError):
                merged_ledger["category_counts_this_week"][key] = 0

    try:
        merged_ledger["saveable_this_week"] = max(0, int(ledger.get("saveable_this_week", 0)))
    except (TypeError, ValueError):
        merged_ledger["saveable_this_week"] = 0
    stored_week_start = str(ledger.get("week_start", merged_ledger["week_start"]))
    active_week_start = current_week_start()
    rolled_over = stored_week_start != active_week_start
    if rolled_over:
        merged_ledger["category_counts_this_week"] = {
            "authority": 0,
            "translation": 0,
            "personal": 0,
            "growth": 0,
        }
        merged_ledger["saveable_this_week"] = 0
        merged_ledger["week_start"] = active_week_start
    else:
        merged_ledger["week_start"] = stored_week_start

    merged["content_ledger"] = merged_ledger
    return merged, rolled_over


def load_state(path: Path, *, fallback_last_sha: str | None = None) -> tuple[dict[str, Any], bool, bool]:
    """Load state from disk. Returns (state, recovered, rolled_over)."""
    if not path.exists():
        return default_state(last_commit_sha=fallback_last_sha), True, False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("state.json root must be an object")
        normalized, rolled_over = _normalize_state(raw)
        if fallback_last_sha and not normalized.get("last_commit_sha"):
            normalized["last_commit_sha"] = fallback_last_sha
        return normalized, False, rolled_over
    except Exception:
        return default_state(last_commit_sha=fallback_last_sha), True, False


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Write state atomically."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized, _ = _normalize_state(state)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(path)
    except Exception as exc:
        raise BuildLogStateError(f"Failed to save state at {path}: {exc}") from exc


def reset_state(path: Path, *, last_commit_sha: str | None = None) -> dict[str, Any]:
    """Reset state to defaults and persist."""
    state = default_state(last_commit_sha=last_commit_sha)
    save_state(path, state)
    return state
