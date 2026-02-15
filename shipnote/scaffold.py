"""Bootstrap helpers for one-command Shipnote setup."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .config_loader import (
    RepoConfig,
    _deep_merge_dicts,
    _default_repo_config_values,
    _parse_yaml_subset,
    _validate_repo_config,
    default_global_defaults_path,
)
from .errors import ShipnoteConfigError
from .git_cli import ensure_git_repo

DEFAULT_TEMPLATE_ORDER = [
    "authority",
    "translation",
    "personal",
    "growth",
    "thread",
    "weekly_wrapup",
]


@dataclass(frozen=True)
class BootstrapResult:
    """Outputs from repo bootstrap."""

    config_path: Path
    created_config: bool
    updated_config: bool
    template_count_written: int
    git_initialized: bool


def _yaml_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _repo_relative_path(repo_root: Path, value: Path) -> str:
    return str(value.resolve().relative_to(repo_root.resolve()))


def _ordered_template_keys(values: dict[str, Any]) -> list[str]:
    ordered = [key for key in DEFAULT_TEMPLATE_ORDER if key in values]
    extras = sorted([key for key in values.keys() if key not in DEFAULT_TEMPLATE_ORDER])
    return ordered + extras


def _config_yaml_from_repo_config(repo_cfg: RepoConfig) -> str:
    template_categories = repo_cfg.template_preferences.content_category_default_by_template
    thread_eligibility = repo_cfg.template_preferences.is_thread_eligible_by_template
    lines: list[str] = [
        f"project_name: {_yaml_quote(repo_cfg.project_name)}",
        f"project_description: {_yaml_quote(repo_cfg.project_description)}",
        f"voice_description: {_yaml_quote(repo_cfg.voice_description)}",
        "",
        f"poll_interval_seconds: {repo_cfg.poll_interval_seconds}",
        f"max_drafts_per_commit: {repo_cfg.max_drafts_per_commit}",
        f"lookback_commits: {repo_cfg.lookback_commits}",
        "",
        f'template_dir: "{_repo_relative_path(repo_cfg.repo_root, repo_cfg.template_dir)}"',
        f'queue_dir: "{_repo_relative_path(repo_cfg.repo_root, repo_cfg.queue_dir)}"',
        f'archive_dir: "{_repo_relative_path(repo_cfg.repo_root, repo_cfg.archive_dir)}"',
        "",
        "context:",
        "  additional_files:",
        *[f'    - "{path}"' for path in repo_cfg.context.additional_files],
        f"  max_total_chars: {repo_cfg.context.max_total_chars}",
        "",
        "content_policy:",
        "  focus_topics:",
        *[f'    - "{topic}"' for topic in repo_cfg.content_policy.focus_topics],
        "  avoid_topics:",
        *[f'    - "{topic}"' for topic in repo_cfg.content_policy.avoid_topics],
        f"  engagement_reminder: {_yaml_quote(repo_cfg.content_policy.engagement_reminder)}",
        "",
        "template_preferences:",
        "  content_category_default_by_template:",
    ]
    lines.extend(
        [
            f"    {template}: {_yaml_quote(template_categories[template])}"
            for template in _ordered_template_keys(template_categories)
        ]
    )
    lines.extend(
        [
            "  is_thread_eligible_by_template:",
            *[
                f"    {template}: {str(thread_eligibility[template]).lower()}"
                for template in _ordered_template_keys(thread_eligibility)
            ],
            "",
            "skip_patterns:",
            "  messages:",
        ]
    )
    lines.extend([f'    - "{pattern}"' for pattern in repo_cfg.skip_patterns.messages])
    lines.extend(
        [
            "  files_only:",
            *[f'    - "{pattern}"' for pattern in repo_cfg.skip_patterns.files_only],
            f"  min_meaningful_files: {repo_cfg.skip_patterns.min_meaningful_files}",
            "",
            "content_balance:",
            f"  authority: {repo_cfg.content_balance.authority}",
            f"  translation: {repo_cfg.content_balance.translation}",
            f"  personal: {repo_cfg.content_balance.personal}",
            f"  growth: {repo_cfg.content_balance.growth}",
            "",
            "secret_patterns:",
            *[f'  - "{pattern}"' for pattern in repo_cfg.secret_patterns],
            "",
        ]
    )
    return "\n".join(lines)


def _load_optional_global_defaults() -> dict[str, Any]:
    defaults_path = default_global_defaults_path()
    if not defaults_path.exists():
        return {}
    if not defaults_path.is_file():
        raise ShipnoteConfigError(f"Global defaults path is not a file: {defaults_path}")
    parsed = _parse_yaml_subset(defaults_path)
    if not isinstance(parsed, dict):
        raise ShipnoteConfigError(f"Global defaults root must be an object: {defaults_path}")
    return parsed


def _resolve_config_path(repo: Path, config_path_override: str | Path | None) -> Path:
    if config_path_override is None:
        return repo / ".shipnote" / "config.yaml"

    candidate = Path(config_path_override).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()
    try:
        resolved.relative_to(repo.resolve())
    except ValueError as exc:
        raise ShipnoteConfigError(
            f"Config path must be inside repository root {repo}: {resolved}"
        ) from exc
    return resolved


def _ensure_git_repo(repo_path: Path, *, init_git: bool) -> bool:
    try:
        ensure_git_repo(repo_path)
        return False
    except Exception:
        if not init_git:
            raise ShipnoteConfigError(
                f"Target path is not a git repository: {repo_path}. "
                "Run `git init` or pass --init-git."
            )
        result = subprocess.run(
            ["git", "init", "-q"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ShipnoteConfigError(
                f"Failed to initialize git repository at {repo_path}: "
                f"{result.stderr.strip() or 'unknown error'}"
            )
        return True


def _write_text_atomic(path: Path, content: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def _bundled_template_paths() -> list[resources.abc.Traversable]:
    root = resources.files("shipnote.assets.templates")
    return sorted(
        [item for item in root.iterdir() if item.name.endswith(".md")],
        key=lambda item: item.name,
    )


def bootstrap_repo(
    *,
    repo_path: Path,
    project_name: str | None = None,
    project_description: str | None = None,
    voice_description: str | None = None,
    poll_interval_seconds: int | None = None,
    force: bool = False,
    init_git: bool = False,
    config_path_override: str | Path | None = None,
    config_overrides: dict[str, Any] | None = None,
    use_global_defaults: bool = True,
) -> BootstrapResult:
    """Create or update Shipnote repo scaffolding in a target project."""
    repo = repo_path.expanduser().resolve()
    if not repo.exists() or not repo.is_dir():
        raise ShipnoteConfigError(f"Target repo path does not exist or is not a directory: {repo}")

    git_initialized = _ensure_git_repo(repo, init_git=init_git)
    config_path = _resolve_config_path(repo, config_path_override)

    raw_values = _default_repo_config_values(repo)
    if use_global_defaults:
        raw_values = _deep_merge_dicts(raw_values, _load_optional_global_defaults())
    if config_overrides:
        raw_values = _deep_merge_dicts(raw_values, config_overrides)
    if project_name is not None:
        raw_values["project_name"] = project_name
    if project_description is not None:
        raw_values["project_description"] = project_description
    if voice_description is not None:
        raw_values["voice_description"] = voice_description
    if poll_interval_seconds is not None:
        raw_values["poll_interval_seconds"] = max(1, poll_interval_seconds)

    resolved_cfg = _validate_repo_config(raw_values, repo, config_path)
    config_content = _config_yaml_from_repo_config(resolved_cfg)

    resolved_cfg.shipnote_dir.mkdir(parents=True, exist_ok=True)
    resolved_cfg.template_dir.mkdir(parents=True, exist_ok=True)
    resolved_cfg.queue_dir.mkdir(parents=True, exist_ok=True)
    resolved_cfg.archive_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    created_config = False
    updated_config = False
    if config_path.exists():
        if force:
            _write_text_atomic(config_path, config_content)
            updated_config = True
    else:
        _write_text_atomic(config_path, config_content)
        created_config = True

    written_count = 0
    for bundled in _bundled_template_paths():
        target = resolved_cfg.template_dir / bundled.name
        if target.exists() and not force:
            continue
        _write_text_atomic(target, bundled.read_text(encoding="utf-8"))
        written_count += 1

    return BootstrapResult(
        config_path=config_path,
        created_config=created_config,
        updated_config=updated_config,
        template_count_written=written_count,
        git_initialized=git_initialized,
    )
