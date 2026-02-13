"""Secret scanning and redaction."""

from __future__ import annotations

import re

REDACTION_TOKEN = "[REDACTED]"


def redact_diff(diff_text: str, secret_patterns: list[str] | None = None) -> tuple[str, int]:
    """Redact secret-like content using configured regex patterns."""
    patterns = secret_patterns or []
    sanitized = diff_text
    total_redactions = 0

    for pattern in patterns:
        try:
            sanitized, redactions = re.subn(pattern, REDACTION_TOKEN, sanitized)
        except re.error:
            # Pattern validation happens at config load; skip defensively here.
            continue
        total_redactions += redactions

    return sanitized, total_redactions
