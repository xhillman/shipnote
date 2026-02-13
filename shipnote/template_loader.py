"""Template loading and minimal frontmatter validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ShipnoteConfigError

STANDARD_TEMPLATE_FILES = (
    "authority.md",
    "translation.md",
    "personal.md",
    "growth.md",
    "thread.md",
    "weekly_wrapup.md",
)


@dataclass(frozen=True)
class TemplateDocument:
    """Loaded markdown template with parsed frontmatter."""

    filename: str
    path: Path
    frontmatter: dict[str, Any]
    body: str
    raw: str


def _parse_frontmatter(raw: str, filename: str) -> tuple[dict[str, Any], str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ShipnoteConfigError(f"Template '{filename}' is missing YAML frontmatter.")

    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ShipnoteConfigError(f"Template '{filename}' has unclosed YAML frontmatter.")

    frontmatter_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    frontmatter: dict[str, Any] = {}
    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        frontmatter[key.strip()] = value.strip()

    if "content_type" not in frontmatter:
        raise ShipnoteConfigError(f"Template '{filename}' frontmatter missing 'content_type'.")
    if "name" not in frontmatter:
        raise ShipnoteConfigError(f"Template '{filename}' frontmatter missing 'name'.")

    return frontmatter, body


def load_templates(template_dir: Path) -> dict[str, TemplateDocument]:
    """Load all markdown templates from a directory."""
    if not template_dir.exists() or not template_dir.is_dir():
        raise ShipnoteConfigError(f"Template directory not found: {template_dir}")

    paths = sorted(template_dir.glob("*.md"))
    if not paths:
        raise ShipnoteConfigError(f"Template directory is empty: {template_dir}")

    templates: dict[str, TemplateDocument] = {}
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(raw, path.name)
        templates[path.name] = TemplateDocument(
            filename=path.name,
            path=path,
            frontmatter=frontmatter,
            body=body,
            raw=raw,
        )
    return templates


def missing_standard_templates(templates: dict[str, TemplateDocument]) -> list[str]:
    """Return standard template filenames that are not present."""
    present = set(templates.keys())
    return [name for name in STANDARD_TEMPLATE_FILES if name not in present]

