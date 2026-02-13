"""Heuristic filtering for commit significance."""

from __future__ import annotations

import re
from fnmatch import fnmatch

from .config_loader import SkipPatternsConfig


def _matches_any_message_pattern(message: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if re.search(pattern, message, flags=re.IGNORECASE):
            return pattern
    return None


def _matches_any_file_pattern(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def should_keep_commit(
    commit_message: str,
    files_changed: list[str],
    skip_config: SkipPatternsConfig,
) -> tuple[bool, str]:
    """Apply skip heuristics in defined order."""
    matched_pattern = _matches_any_message_pattern(commit_message, skip_config.messages)
    if matched_pattern is not None:
        return False, f"message matched skip pattern '{matched_pattern}'"

    meaningful_files = [
        path for path in files_changed if not _matches_any_file_pattern(path, skip_config.files_only)
    ]
    if len(meaningful_files) < skip_config.min_meaningful_files:
        return (
            False,
            "insufficient meaningful files "
            f"({len(meaningful_files)} < {skip_config.min_meaningful_files})",
        )

    return True, f"kept ({len(meaningful_files)} meaningful file(s))"
