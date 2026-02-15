"""Bootstrap helpers for one-command Shipnote setup."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .config_loader import (
    DEFAULT_AVOID_TOPICS,
    DEFAULT_CONTEXT_ADDITIONAL_FILES,
    DEFAULT_CONTEXT_MAX_TOTAL_CHARS,
    DEFAULT_ENGAGEMENT_REMINDER,
    DEFAULT_FOCUS_TOPICS,
)
from .errors import ShipnoteConfigError
from .git_cli import ensure_git_repo

DEFAULT_VOICE_DESCRIPTION = (
    "Technical but accessible. Practical engineering tone. Direct, no fluff. "
    "Occasional dry humor."
)
DEFAULT_SKIP_MESSAGE_PATTERNS = [
    "^wip",
    "^fix typo",
    "^merge branch",
    "^bump",
    "^chore:",
    "^Merge pull request",
    "^Initial commit$",
]
DEFAULT_SKIP_FILES_ONLY = [
    "package-lock.json",
    "yarn.lock",
    "*.lock",
    ".env*",
    ".gitignore",
    "*.min.js",
    "*.min.css",
]
DEFAULT_SECRET_PATTERNS = [
    "(sk-[a-zA-Z0-9]{20,})",
    "(AKIA[A-Z0-9]{16})",
    "(ghp_[a-zA-Z0-9]{36})",
    "(sk_live_[a-zA-Z0-9]{24,})",
    "(pk_live_[a-zA-Z0-9]{24,})",
    "([Bb]earer\\s+[a-zA-Z0-9._~+/-]+=*)",
    "(xox[bpsa]-[a-zA-Z0-9-]+)",
    "([a-zA-Z0-9+/]{40,}={0,2})",
    "password\\s*[:=]\\s*[\"']?([^\"'\\s]+)",
    "secret\\s*[:=]\\s*[\"']?([^\"'\\s]+)",
]
DEFAULT_CONTEXT_FILES = list(DEFAULT_CONTEXT_ADDITIONAL_FILES)
DEFAULT_CONTEXT_CHARS = DEFAULT_CONTEXT_MAX_TOTAL_CHARS
DEFAULT_CONTENT_FOCUS_TOPICS = list(DEFAULT_FOCUS_TOPICS)
DEFAULT_CONTENT_AVOID_TOPICS = list(DEFAULT_AVOID_TOPICS)
DEFAULT_CONTENT_ENGAGEMENT_REMINDER = DEFAULT_ENGAGEMENT_REMINDER


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


def _default_config_yaml(
    *,
    project_name: str,
    project_description: str,
    voice_description: str,
    poll_interval_seconds: int,
) -> str:
    lines: list[str] = [
        f"project_name: {_yaml_quote(project_name)}",
        f"project_description: {_yaml_quote(project_description)}",
        f"voice_description: {_yaml_quote(voice_description)}",
        "",
        f"poll_interval_seconds: {max(1, poll_interval_seconds)}",
        "max_drafts_per_commit: 3",
        "lookback_commits: 10",
        "",
        'template_dir: ".shipnote/templates"',
        'queue_dir: ".shipnote/queue"',
        'archive_dir: ".shipnote/archive"',
        "",
        "context:",
        "  additional_files:",
        *[f'    - "{path}"' for path in DEFAULT_CONTEXT_FILES],
        f"  max_total_chars: {DEFAULT_CONTEXT_CHARS}",
        "",
        "content_policy:",
        "  focus_topics:",
        *[f'    - "{topic}"' for topic in DEFAULT_CONTENT_FOCUS_TOPICS],
        "  avoid_topics:",
        *[f'    - "{topic}"' for topic in DEFAULT_CONTENT_AVOID_TOPICS],
        f"  engagement_reminder: {_yaml_quote(DEFAULT_CONTENT_ENGAGEMENT_REMINDER)}",
        "",
        "skip_patterns:",
        "  messages:",
    ]
    lines.extend([f'    - "{pattern}"' for pattern in DEFAULT_SKIP_MESSAGE_PATTERNS])
    lines.extend(
        [
            "  files_only:",
            *[f'    - "{pattern}"' for pattern in DEFAULT_SKIP_FILES_ONLY],
            "  min_meaningful_files: 1",
            "",
            "content_balance:",
            "  authority: 30",
            "  translation: 25",
            "  personal: 25",
            "  growth: 20",
            "",
            "secret_patterns:",
            *[f'  - "{pattern}"' for pattern in DEFAULT_SECRET_PATTERNS],
            "",
        ]
    )
    return "\n".join(lines)


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
    poll_interval_seconds: int = 60,
    force: bool = False,
    init_git: bool = False,
) -> BootstrapResult:
    """Create or update Shipnote repo scaffolding in a target project."""
    repo = repo_path.expanduser().resolve()
    if not repo.exists() or not repo.is_dir():
        raise ShipnoteConfigError(f"Target repo path does not exist or is not a directory: {repo}")

    git_initialized = _ensure_git_repo(repo, init_git=init_git)

    shipnote_dir = repo / ".shipnote"
    templates_dir = shipnote_dir / "templates"
    queue_dir = shipnote_dir / "queue"
    archive_dir = shipnote_dir / "archive"
    shipnote_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)
    queue_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    effective_project_name = project_name or repo.name
    effective_description = (
        project_description
        or f"Shipnote-enabled project at {repo.name}."
    )
    effective_voice = voice_description or DEFAULT_VOICE_DESCRIPTION
    config_path = shipnote_dir / "config.yaml"
    config_content = _default_config_yaml(
        project_name=effective_project_name,
        project_description=effective_description,
        voice_description=effective_voice,
        poll_interval_seconds=poll_interval_seconds,
    )

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
        target = templates_dir / bundled.name
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
