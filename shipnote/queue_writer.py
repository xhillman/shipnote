"""Queue markdown writer and ledger updater."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config_loader import RepoConfig
from .git_cli import CommitInfo
from .state_manager import utc_now

AVAILABILITY_REMINDER = "Be available for 60 min after posting. Reply to every reply substantively."
SPACING_REMINDER = "Space 2-3 hours from last post. Max 2-4 posts/day."


def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _atomic_write(path: Path, content: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def _slugify_commit_message(message: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", message.lower()).strip("-")
    if len(slug) > 50:
        slug = slug[:50].rstrip("-")
    return slug or "commit"


def _ensure_ledger_shape(state: dict[str, Any]) -> dict[str, Any]:
    ledger = state.setdefault("content_ledger", {})
    ledger.setdefault("recent_drafts", [])
    ledger.setdefault(
        "category_counts_this_week",
        {"authority": 0, "translation": 0, "personal": 0, "growth": 0},
    )
    ledger.setdefault("saveable_this_week", 0)
    return ledger


def _thread_tweet_count(content: str) -> int:
    if not content.strip():
        return 0
    blocks = [chunk.strip() for chunk in content.split("\n---\n") if chunk.strip()]
    return len(blocks) if blocks else 1


def _render_frontmatter(
    *,
    queue_number: int,
    draft: dict[str, Any],
    commit: CommitInfo,
    project_name: str,
    engagement_reminder: str,
    generated_at: str,
) -> str:
    signals = ", ".join(str(s) for s in draft.get("target_signals", []))
    lines = [
        "---",
        f"queue: {queue_number}",
        f"template: {draft.get('template_type')}",
        f"category: {_yaml_quote(str(draft.get('content_category')))}",
        f"suggested_time: {draft.get('suggested_time')}",
        f"target_signals: [{signals}]",
        f"is_thread: {str(bool(draft.get('is_thread', False))).lower()}",
        f"commit: {commit.sha}",
        f"commit_message: {_yaml_quote(commit.message)}",
        f"generated_at: {_yaml_quote(generated_at)}",
        f"project: {project_name}",
        f"engagement_reminder: {_yaml_quote(engagement_reminder)}",
        f"availability_reminder: {_yaml_quote(AVAILABILITY_REMINDER)}",
        f"spacing_reminder: {_yaml_quote(SPACING_REMINDER)}",
    ]
    if bool(draft.get("is_thread", False)):
        lines.append(f"tweet_count: {_thread_tweet_count(str(draft.get('content', '')))}")
    lines.append("---")
    return "\n".join(lines)


def write_drafts(
    *,
    drafts: list[dict[str, Any]],
    state: dict[str, Any],
    repo_cfg: RepoConfig,
    commit: CommitInfo,
) -> list[Path]:
    """Write generated drafts to queue and update in-memory state."""
    queue_dir = repo_cfg.queue_dir
    queue_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    ledger = _ensure_ledger_shape(state)

    for draft in drafts:
        state["queue_counter"] = int(state.get("queue_counter", 0)) + 1
        queue_number = int(state["queue_counter"])
        generated_at = utc_now()
        date_part = generated_at.split("T", 1)[0]
        slug = _slugify_commit_message(commit.message)
        template_type = str(draft.get("template_type", "draft"))
        filename = f"{queue_number:03d}_{date_part}_{slug}_{template_type}.md"
        output_path = queue_dir / filename

        frontmatter = _render_frontmatter(
            queue_number=queue_number,
            draft=draft,
            commit=commit,
            project_name=repo_cfg.project_name,
            engagement_reminder=repo_cfg.content_policy.engagement_reminder,
            generated_at=generated_at,
        )
        body = str(draft.get("content", "")).strip()
        markdown = f"{frontmatter}\n\n{body}\n"
        _atomic_write(output_path, markdown)
        written_paths.append(output_path)

        ledger["recent_drafts"].append(
            {
                "queue_number": queue_number,
                "commit_sha": commit.sha,
                "template_type": template_type,
                "content_category": str(draft.get("content_category", "")),
                "generated_at": generated_at,
                "is_thread": bool(draft.get("is_thread", False)),
            }
        )
        counts = ledger["category_counts_this_week"]
        if template_type in counts:
            counts[template_type] = int(counts.get(template_type, 0)) + 1
        if template_type == "translation":
            ledger["saveable_this_week"] = int(ledger.get("saveable_this_week", 0)) + 1

    return written_paths
