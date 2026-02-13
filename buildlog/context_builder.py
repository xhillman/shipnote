"""Context builder for generation payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config_loader import RepoConfig
from .git_cli import CommitInfo

MAX_DIFF_SUMMARY_CHARS = 12000


def _normalize_commit_date(date_text: str) -> str:
    """Normalize git date format to RFC3339 UTC when possible."""
    try:
        dt = datetime.strptime(date_text.strip(), "%Y-%m-%d %H:%M:%S %z")
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        return date_text


def _balance_recommendation(target: dict[str, int], actual: dict[str, int]) -> str:
    total_actual = sum(max(0, int(actual.get(key, 0))) for key in target)
    if total_actual <= 0:
        highest = max(target, key=target.get)
        return (
            "No content tracked this week yet. "
            f"Start with {highest.capitalize()} content to establish baseline mix."
        )

    deficits: dict[str, float] = {}
    for key, target_pct in target.items():
        actual_pct = (max(0, int(actual.get(key, 0))) / total_actual) * 100.0
        deficits[key] = float(target_pct) - actual_pct

    recommended = max(deficits, key=deficits.get)
    if deficits[recommended] <= 0:
        return "Content mix is currently balanced. Choose the template that best fits the commit."
    return (
        f"{recommended.capitalize()} content is underrepresented. "
        f"Consider a {recommended}-type draft if the commit supports it."
    )


def _saveable_reminder(state: dict[str, Any]) -> str:
    ledger = state.get("content_ledger", {})
    count = int(ledger.get("saveable_this_week", 0) or 0)
    if count >= 1:
        return f"{count} saveable (Translation) piece generated this week. Target: 1/week. ✓ On track."
    return "0 saveable (Translation) pieces generated this week. Target: 1/week. Consider translation content."


def build_context(
    *,
    repo_cfg: RepoConfig,
    commit: CommitInfo,
    files_changed: list[str],
    sanitized_diff: str,
    current_branch: str,
    recent_history: list[str],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Build context object for the generation stage."""
    target_balance = repo_cfg.content_balance.as_dict()
    ledger = state.get("content_ledger", {})
    actual_balance = ledger.get("category_counts_this_week", {})
    recommendation = _balance_recommendation(target_balance, actual_balance)

    diff_summary = sanitized_diff
    if len(diff_summary) > MAX_DIFF_SUMMARY_CHARS:
        diff_summary = (
            diff_summary[:MAX_DIFF_SUMMARY_CHARS]
            + "\n\n[Diff truncated for context size limits]"
        )

    return {
        "project": {
            "name": repo_cfg.project_name,
            "description": repo_cfg.project_description,
            "current_branch": current_branch,
        },
        "current_commit": {
            "sha": commit.sha,
            "message": commit.message,
            "author": commit.author,
            "date": _normalize_commit_date(commit.date),
            "files_changed": files_changed,
            "diff_summary": diff_summary,
        },
        "recent_history": recent_history,
        "content_balance": {
            "target": target_balance,
            "actual_this_week": actual_balance,
            "recommendation": recommendation,
        },
        "saveable_reminder": _saveable_reminder(state),
    }
