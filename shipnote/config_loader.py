"""Config and secrets loading for Shipnote."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ShipnoteConfigError, ShipnoteSecretsError

DEFAULT_CONFIG_PATH = ".shipnote/config.yaml"
DEFAULT_TEMPLATE_DIR = ".shipnote/templates"
DEFAULT_QUEUE_DIR = ".shipnote/queue"
DEFAULT_ARCHIVE_DIR = ".shipnote/archive"
DEFAULT_CONTEXT_ADDITIONAL_FILES = [".shipnote/context.md"]
DEFAULT_CONTEXT_MAX_TOTAL_CHARS = 12000
DEFAULT_FOCUS_TOPICS = ["software engineering", "developer productivity"]
DEFAULT_AVOID_TOPICS = ["politics", "sports", "crypto"]
DEFAULT_ENGAGEMENT_REMINDER = "Engage in relevant community discussions before and after posting."
AXIS_PROVIDER_API_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
AXIS_MODEL_KEY = "AXIS_DEFAULT_MODEL"


@dataclass(frozen=True)
class SkipPatternsConfig:
    """Heuristic skip-pattern settings from config."""

    messages: list[str]
    files_only: list[str]
    min_meaningful_files: int


@dataclass(frozen=True)
class ContentBalanceConfig:
    """Content balance percentages from config."""

    authority: int
    translation: int
    personal: int
    growth: int

    def as_dict(self) -> dict[str, int]:
        return {
            "authority": self.authority,
            "translation": self.translation,
            "personal": self.personal,
            "growth": self.growth,
        }


@dataclass(frozen=True)
class ContextConfig:
    """Additional context-file settings from config."""

    additional_files: list[str]
    max_total_chars: int


@dataclass(frozen=True)
class ContentPolicyConfig:
    """Content policy settings from config."""

    focus_topics: list[str]
    avoid_topics: list[str]
    engagement_reminder: str


@dataclass(frozen=True)
class RepoConfig:
    """Resolved repository-level config paths and settings."""

    config_path: Path
    repo_root: Path
    shipnote_dir: Path
    project_name: str
    project_description: str
    voice_description: str
    poll_interval_seconds: int
    max_drafts_per_commit: int
    lookback_commits: int
    template_dir: Path
    queue_dir: Path
    archive_dir: Path
    skip_patterns: SkipPatternsConfig
    content_balance: ContentBalanceConfig
    secret_patterns: list[str]
    raw_config: dict[str, Any]
    context: ContextConfig = field(
        default_factory=lambda: ContextConfig(
            additional_files=list(DEFAULT_CONTEXT_ADDITIONAL_FILES),
            max_total_chars=DEFAULT_CONTEXT_MAX_TOTAL_CHARS,
        )
    )
    content_policy: ContentPolicyConfig = field(
        default_factory=lambda: ContentPolicyConfig(
            focus_topics=list(DEFAULT_FOCUS_TOPICS),
            avoid_topics=list(DEFAULT_AVOID_TOPICS),
            engagement_reminder=DEFAULT_ENGAGEMENT_REMINDER,
        )
    )


@dataclass(frozen=True)
class SecretsConfig:
    """Resolved secrets file and parsed env values."""

    secrets_path: Path
    values: dict[str, str]
    mode_octal: str
    permissions_ok: bool


def resolve_repo_root(config_path: Path) -> Path:
    """Resolve repo root from config path."""
    parent = config_path.parent
    if parent.name == ".shipnote":
        return parent.parent
    return parent


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    result: list[str] = []
    for char in value:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\":
            result.append(char)
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            continue
        if char == "#" and not in_single and not in_double:
            break
        result.append(char)
    return "".join(result).rstrip()


def _parse_scalar(value: str) -> Any:
    raw = _strip_quotes(value.strip())
    if raw == "":
        return ""
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def _collect_yaml_lines(path: Path) -> list[tuple[int, int, str]]:
    entries: list[tuple[int, int, str]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw_line.lstrip().startswith("#") or not raw_line.strip():
            continue
        leading = len(raw_line) - len(raw_line.lstrip(" "))
        if "\t" in raw_line[:leading]:
            raise ShipnoteConfigError(
                f"Invalid tab indentation in {path} at line {line_no}. Use spaces only."
            )
        cleaned = _strip_inline_comment(raw_line).rstrip()
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        text = cleaned[indent:]
        entries.append((line_no, indent, text))
    return entries


def _parse_yaml_subset(path: Path) -> dict[str, Any]:
    """Parse a constrained YAML subset sufficient for Shipnote config."""
    entries = _collect_yaml_lines(path)
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]

    for idx, (line_no, indent, text) in enumerate(entries):
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        next_entry = entries[idx + 1] if idx + 1 < len(entries) else None
        next_is_child = bool(next_entry and next_entry[1] > indent)
        next_is_list = bool(next_is_child and next_entry and next_entry[2].startswith("- "))

        if text.startswith("- "):
            if not isinstance(parent, list):
                raise ShipnoteConfigError(
                    f"Unexpected list item in {path} at line {line_no}: no parent list context."
                )
            item_text = text[2:].strip()
            if item_text == "":
                child: dict[str, Any] | list[Any] = [] if next_is_list else {}
                parent.append(child)
                if next_is_child:
                    stack.append((indent, child))
                continue
            parent.append(_parse_scalar(item_text))
            continue

        if ":" not in text:
            raise ShipnoteConfigError(
                f"Invalid config line in {path} at line {line_no}: expected 'key: value'."
            )
        key, remainder = text.split(":", 1)
        key = key.strip()
        if not key:
            raise ShipnoteConfigError(f"Invalid empty key in {path} at line {line_no}.")
        if not isinstance(parent, dict):
            raise ShipnoteConfigError(
                f"Invalid mapping entry in {path} at line {line_no}: parent is not an object."
            )
        remainder = remainder.strip()
        if remainder == "":
            child_obj: dict[str, Any] | list[Any] = [] if next_is_list else {}
            parent[key] = child_obj
            if next_is_child:
                stack.append((indent, child_obj))
            continue

        parent[key] = _parse_scalar(remainder)

    return root


def _as_dict(raw: Any, key: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ShipnoteConfigError(f"Config key '{key}' must be an object.")
    return raw


def _as_str(raw: Any, key: str, *, default: str | None = None) -> str:
    if raw is None and default is not None:
        return default
    if not isinstance(raw, str) or not raw.strip():
        raise ShipnoteConfigError(f"Config key '{key}' must be a non-empty string.")
    return raw


def _as_int(raw: Any, key: str, *, minimum: int = 0, default: int | None = None) -> int:
    if raw is None and default is not None:
        value = default
    elif isinstance(raw, int):
        value = raw
    else:
        raise ShipnoteConfigError(f"Config key '{key}' must be an integer.")
    if value < minimum:
        raise ShipnoteConfigError(f"Config key '{key}' must be >= {minimum}.")
    return value


def _as_str_list(raw: Any, key: str) -> list[str]:
    if not isinstance(raw, list):
        raise ShipnoteConfigError(f"Config key '{key}' must be a list.")
    out: list[str] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, str):
            raise ShipnoteConfigError(f"Config key '{key}[{idx}]' must be a string.")
        out.append(item)
    return out


def _validate_non_empty_strings(values: list[str], key: str) -> None:
    if not values:
        raise ShipnoteConfigError(f"Config key '{key}' must contain at least one value.")
    for idx, item in enumerate(values):
        if not item.strip():
            raise ShipnoteConfigError(f"Config key '{key}[{idx}]' must be a non-empty string.")


def _as_non_empty_str_list(raw: Any, key: str, *, default: list[str]) -> list[str]:
    values = _as_str_list(raw if raw is not None else list(default), key)
    _validate_non_empty_strings(values, key)
    return values


def _ensure_relative_repo_path(repo_root: Path, path_value: str, key: str) -> Path:
    rel = Path(path_value)
    if rel.is_absolute():
        raise ShipnoteConfigError(f"Config key '{key}' must be a relative path.")
    resolved = (repo_root / rel).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ShipnoteConfigError(
            f"Config key '{key}' resolves outside repository root: {path_value}"
        ) from exc
    return resolved


def _validate_patterns(patterns: list[str], key: str) -> None:
    for idx, pattern in enumerate(patterns):
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ShipnoteConfigError(
                f"Invalid regex in '{key}[{idx}]': {exc}"
            ) from exc


def _validate_repo_config(raw: dict[str, Any], repo_root: Path, config_path: Path) -> RepoConfig:
    project_name = _as_str(raw.get("project_name"), "project_name")
    project_description = _as_str(raw.get("project_description"), "project_description")
    voice_description = _as_str(raw.get("voice_description"), "voice_description")

    poll_interval_seconds = _as_int(
        raw.get("poll_interval_seconds"), "poll_interval_seconds", minimum=1, default=60
    )
    max_drafts_per_commit = _as_int(
        raw.get("max_drafts_per_commit"), "max_drafts_per_commit", minimum=1, default=3
    )
    lookback_commits = _as_int(raw.get("lookback_commits"), "lookback_commits", minimum=1, default=10)

    template_dir = _ensure_relative_repo_path(
        repo_root, _as_str(raw.get("template_dir"), "template_dir", default=DEFAULT_TEMPLATE_DIR), "template_dir"
    )
    queue_dir = _ensure_relative_repo_path(
        repo_root, _as_str(raw.get("queue_dir"), "queue_dir", default=DEFAULT_QUEUE_DIR), "queue_dir"
    )
    archive_dir = _ensure_relative_repo_path(
        repo_root, _as_str(raw.get("archive_dir"), "archive_dir", default=DEFAULT_ARCHIVE_DIR), "archive_dir"
    )

    skip_raw = _as_dict(raw.get("skip_patterns"), "skip_patterns")
    skip_messages = _as_str_list(skip_raw.get("messages"), "skip_patterns.messages")
    skip_files_only = _as_str_list(skip_raw.get("files_only"), "skip_patterns.files_only")
    min_meaningful_files = _as_int(
        skip_raw.get("min_meaningful_files"),
        "skip_patterns.min_meaningful_files",
        minimum=0,
        default=1,
    )
    _validate_patterns(skip_messages, "skip_patterns.messages")
    skip_patterns = SkipPatternsConfig(
        messages=skip_messages,
        files_only=skip_files_only,
        min_meaningful_files=min_meaningful_files,
    )

    balance_raw = _as_dict(raw.get("content_balance"), "content_balance")
    content_balance = ContentBalanceConfig(
        authority=_as_int(balance_raw.get("authority"), "content_balance.authority", minimum=0),
        translation=_as_int(balance_raw.get("translation"), "content_balance.translation", minimum=0),
        personal=_as_int(balance_raw.get("personal"), "content_balance.personal", minimum=0),
        growth=_as_int(balance_raw.get("growth"), "content_balance.growth", minimum=0),
    )
    if sum(content_balance.as_dict().values()) != 100:
        raise ShipnoteConfigError("content_balance percentages must sum to 100.")

    secret_patterns = _as_str_list(raw.get("secret_patterns"), "secret_patterns")
    _validate_patterns(secret_patterns, "secret_patterns")

    context_raw = _as_dict(raw.get("context", {}), "context")
    additional_files = _as_str_list(
        context_raw.get("additional_files", list(DEFAULT_CONTEXT_ADDITIONAL_FILES)),
        "context.additional_files",
    )
    for idx, path_value in enumerate(additional_files):
        if not path_value.strip():
            raise ShipnoteConfigError(
                f"Config key 'context.additional_files[{idx}]' must be a non-empty string."
            )
    max_total_chars = _as_int(
        context_raw.get("max_total_chars"),
        "context.max_total_chars",
        minimum=1,
        default=DEFAULT_CONTEXT_MAX_TOTAL_CHARS,
    )
    context = ContextConfig(
        additional_files=additional_files,
        max_total_chars=max_total_chars,
    )

    content_policy_raw = _as_dict(raw.get("content_policy", {}), "content_policy")
    focus_topics = _as_non_empty_str_list(
        content_policy_raw.get("focus_topics"),
        "content_policy.focus_topics",
        default=DEFAULT_FOCUS_TOPICS,
    )
    avoid_topics = _as_non_empty_str_list(
        content_policy_raw.get("avoid_topics"),
        "content_policy.avoid_topics",
        default=DEFAULT_AVOID_TOPICS,
    )
    engagement_reminder = _as_str(
        content_policy_raw.get("engagement_reminder"),
        "content_policy.engagement_reminder",
        default=DEFAULT_ENGAGEMENT_REMINDER,
    )
    content_policy = ContentPolicyConfig(
        focus_topics=focus_topics,
        avoid_topics=avoid_topics,
        engagement_reminder=engagement_reminder,
    )

    return RepoConfig(
        config_path=config_path,
        repo_root=repo_root,
        shipnote_dir=(repo_root / ".shipnote").resolve(),
        project_name=project_name,
        project_description=project_description,
        voice_description=voice_description,
        poll_interval_seconds=poll_interval_seconds,
        max_drafts_per_commit=max_drafts_per_commit,
        lookback_commits=lookback_commits,
        template_dir=template_dir,
        queue_dir=queue_dir,
        archive_dir=archive_dir,
        skip_patterns=skip_patterns,
        content_balance=content_balance,
        secret_patterns=secret_patterns,
        context=context,
        content_policy=content_policy,
        raw_config=raw,
    )


def load_repo_config(config_path_str: str) -> RepoConfig:
    """Load and validate repo config."""
    config_path = Path(config_path_str).expanduser().resolve()
    if not config_path.exists():
        raise ShipnoteConfigError(
            f"Config file not found: {config_path}. Create {DEFAULT_CONFIG_PATH} in your repo."
        )
    if not config_path.is_file():
        raise ShipnoteConfigError(f"Config path is not a file: {config_path}")

    parsed = _parse_yaml_subset(config_path)
    repo_root = resolve_repo_root(config_path)
    return _validate_repo_config(parsed, repo_root, config_path)


def default_secrets_path() -> Path:
    """Return the global Shipnote secrets path."""
    return (Path.home() / ".shipnote" / "secrets.env").expanduser().resolve()


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = _strip_inline_comment(line.strip())
        if not raw or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_quotes(value.strip())
    return values


def load_secrets(*, required: bool = True) -> SecretsConfig:
    """Load global secrets file and inject values into process env."""
    path = default_secrets_path()
    if not path.exists():
        if required:
            raise ShipnoteSecretsError(f"Secrets file missing: {path}. Create ~/.shipnote/secrets.env")
        return SecretsConfig(
            secrets_path=path,
            values={},
            mode_octal="0o000",
            permissions_ok=False,
        )
    if not path.is_file():
        raise ShipnoteSecretsError(f"Secrets path is not a file: {path}")

    mode = stat.S_IMODE(path.stat().st_mode)
    mode_octal = oct(mode)
    values = _parse_env_file(path)

    for key, value in values.items():
        if key and value and key not in os.environ:
            os.environ[key] = value

    if required:
        has_provider_key = any(bool(os.getenv(key)) for key in AXIS_PROVIDER_API_KEYS)
        if not has_provider_key:
            joined = ", ".join(AXIS_PROVIDER_API_KEYS)
            raise ShipnoteSecretsError(
                f"Missing axis-core provider API key in {path}. Add one of: {joined}."
            )

    return SecretsConfig(
        secrets_path=path,
        values=values,
        mode_octal=mode_octal,
        permissions_ok=(mode == 0o600),
    )


def ensure_runtime_dirs(repo_cfg: RepoConfig) -> None:
    """Create required runtime dirs."""
    repo_cfg.shipnote_dir.mkdir(parents=True, exist_ok=True)
    repo_cfg.queue_dir.mkdir(parents=True, exist_ok=True)
    repo_cfg.archive_dir.mkdir(parents=True, exist_ok=True)
