"""Config read/edit helpers for CLI config commands."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from . import config_loader
from .errors import ShipnoteConfigError


def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _scalar_to_yaml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _yaml_quote(value)
    raise ShipnoteConfigError(f"Unsupported scalar type in config serialization: {type(value).__name__}")


def _render_yaml_lines(value: Any, *, indent: int = 0, key_path: str = "") -> list[str]:
    prefix = " " * indent

    if isinstance(value, dict):
        if not value:
            raise ShipnoteConfigError(
                f"Cannot serialize empty object at '{key_path or '<root>'}' with current config format."
            )
        lines: list[str] = []
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ShipnoteConfigError("Config keys must be non-empty strings.")
            child_path = f"{key_path}.{key}" if key_path else key
            if isinstance(child, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_render_yaml_lines(child, indent=indent + 2, key_path=child_path))
            else:
                lines.append(f"{prefix}{key}: {_scalar_to_yaml(child)}")
        return lines

    if isinstance(value, list):
        if not value:
            raise ShipnoteConfigError(
                f"Cannot serialize empty list at '{key_path or '<root>'}' with current config format."
            )
        lines = []
        for idx, item in enumerate(value):
            item_path = f"{key_path}[{idx}]"
            if isinstance(item, (dict, list)):
                raise ShipnoteConfigError(
                    f"Nested non-scalar list items are not supported at '{item_path}'."
                )
            lines.append(f"{prefix}- {_scalar_to_yaml(item)}")
        return lines

    raise ShipnoteConfigError(
        f"Cannot serialize non-container root value: {type(value).__name__}"
    )


def _normalize_path(config_path_str: str) -> Path:
    path = Path(config_path_str).expanduser().resolve()
    if not path.exists():
        raise ShipnoteConfigError(
            f"Config file not found: {path}. Create {config_loader.DEFAULT_CONFIG_PATH} in your repo."
        )
    if not path.is_file():
        raise ShipnoteConfigError(f"Config path is not a file: {path}")
    return path


def _load_raw_config(path: Path) -> dict[str, Any]:
    parsed = config_loader._parse_yaml_subset(path)
    if not isinstance(parsed, dict):
        raise ShipnoteConfigError(f"Config root must be an object: {path}")
    return parsed


def _split_key_path(key_path: str) -> list[str]:
    keys = [part.strip() for part in key_path.split(".") if part.strip()]
    if not keys:
        raise ShipnoteConfigError("Config key path must be non-empty (example: content_policy.focus_topics).")
    return keys


def _get_by_path(data: dict[str, Any], key_path: str) -> Any:
    current: Any = data
    for key in _split_key_path(key_path):
        if not isinstance(current, dict) or key not in current:
            raise ShipnoteConfigError(f"Config key not found: {key_path}")
        current = current[key]
    return current


def _set_by_path(data: dict[str, Any], key_path: str, value: Any) -> None:
    keys = _split_key_path(key_path)
    current: dict[str, Any] = data
    for key in keys[:-1]:
        existing = current.get(key)
        if existing is None:
            current[key] = {}
            existing = current[key]
        if not isinstance(existing, dict):
            raise ShipnoteConfigError(f"Cannot set nested key under non-object: {'.'.join(keys[:-1])}")
        current = existing
    current[keys[-1]] = value


def _unset_by_path(data: dict[str, Any], key_path: str) -> None:
    keys = _split_key_path(key_path)
    chain: list[tuple[dict[str, Any], str]] = []
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ShipnoteConfigError(f"Config key not found: {key_path}")
        chain.append((current, key))
        current = current[key]

    parent, leaf = chain[-1]
    del parent[leaf]

    # Prune now-empty parent objects to keep serialization valid.
    for parent_obj, key in reversed(chain[:-1]):
        child = parent_obj.get(key)
        if isinstance(child, dict) and not child:
            del parent_obj[key]


def _parse_cli_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if value == "":
        return ""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = None
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        return raw_value

    if isinstance(parsed, float):
        raise ShipnoteConfigError("Floating-point values are not supported in config.")
    if isinstance(parsed, (dict, list, bool, int, str)):
        return parsed
    if parsed is None:
        raise ShipnoteConfigError("Null values are not supported. Use `unset` to remove keys.")
    raise ShipnoteConfigError(f"Unsupported value type: {type(parsed).__name__}")


def _validate_and_write(path: Path, raw_config: dict[str, Any]) -> None:
    repo_root = config_loader.resolve_repo_root(path)
    config_loader._validate_repo_config(raw_config, repo_root, path)
    rendered = "\n".join(_render_yaml_lines(raw_config)) + "\n"

    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_text(rendered, encoding="utf-8")
        # Ensure serialized output is parseable by current loader before replace.
        config_loader.load_repo_config(str(temp))
        temp.replace(path)
    except Exception as exc:
        if temp.exists():
            temp.unlink()
        if isinstance(exc, ShipnoteConfigError):
            raise
        raise ShipnoteConfigError(f"Failed to update config at {path}: {exc}") from exc


def list_config_text(config_path_str: str) -> str:
    path = _normalize_path(config_path_str)
    raw = _load_raw_config(path)
    return "\n".join(_render_yaml_lines(raw))


def get_config_value(config_path_str: str, key_path: str) -> Any:
    path = _normalize_path(config_path_str)
    raw = _load_raw_config(path)
    return _get_by_path(raw, key_path)


def set_config_value(config_path_str: str, key_path: str, raw_value: str) -> None:
    path = _normalize_path(config_path_str)
    raw = copy.deepcopy(_load_raw_config(path))
    _set_by_path(raw, key_path, _parse_cli_value(raw_value))
    _validate_and_write(path, raw)


def unset_config_value(config_path_str: str, key_path: str) -> None:
    path = _normalize_path(config_path_str)
    raw = copy.deepcopy(_load_raw_config(path))
    _unset_by_path(raw, key_path)
    _validate_and_write(path, raw)
