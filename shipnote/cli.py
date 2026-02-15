"""Shipnote CLI entrypoints."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config_editor import (
    get_config_value,
    list_config_text,
    set_config_value,
    unset_config_value,
)
from .config_loader import AXIS_MODEL_KEY, DEFAULT_CONFIG_PATH, load_repo_config, load_secrets
from .daemon_runtime import is_pid_alive, read_daemon_status, uptime_seconds
from .errors import ShipnoteError
from .git_cli import ensure_git_repo, get_branch_name, get_head_sha
from .lockfile import exclusive_lock
from .operator import answer_question, run_chat
from .process_loop import run_daemon, run_once
from .scaffold import bootstrap_repo
from .state_manager import load_state, reset_state, state_path
from .template_loader import load_templates, missing_standard_templates


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to repo config (default: .shipnote/config.yaml)",
    )


def _add_bootstrap_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        default=".",
        help="Target repository path (default: current directory)",
    )
    parser.add_argument("--project-name", default=None, help="Project name override")
    parser.add_argument(
        "--project-description",
        default=None,
        help="Project description override",
    )
    parser.add_argument(
        "--voice-description",
        default=None,
        help="Voice description override",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Polling interval in seconds for generated config (default: 60)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite config and templates if they already exist",
    )
    parser.add_argument(
        "--init-git",
        action="store_true",
        help="Initialize git if the target directory is not already a repository",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shipnote")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Run daemon loop")
    _add_config_arg(p_start)

    p_run_once = sub.add_parser("run-once", help="Process new commits once and exit")
    _add_config_arg(p_run_once)

    p_status = sub.add_parser("status", help="Show state summary")
    _add_config_arg(p_status)

    p_reset = sub.add_parser("reset", help="Reset state")
    _add_config_arg(p_reset)

    p_check = sub.add_parser("check", help="Validate config, templates, and secrets")
    _add_config_arg(p_check)

    p_ask = sub.add_parser("ask", help="Ask Shipnote questions")
    _add_config_arg(p_ask)
    p_ask.add_argument("question", help="Question text")

    p_chat = sub.add_parser("chat", help="Interactive Shipnote chat")
    _add_config_arg(p_chat)

    p_init = sub.add_parser("init", help="Bootstrap .shipnote config and templates")
    _add_bootstrap_args(p_init)

    p_launch = sub.add_parser(
        "launch",
        help="Bootstrap (if needed), validate setup, and start daemon",
    )
    _add_bootstrap_args(p_launch)

    p_config = sub.add_parser("config", help="Read or update repo config values")
    _add_config_arg(p_config)
    sub_config = p_config.add_subparsers(dest="config_command", required=True)
    sub_config.add_parser("list", help="Print full config")
    p_config_get = sub_config.add_parser("get", help="Get a config value by dot path")
    p_config_get.add_argument("key", help="Dot-path key (example: content_policy.focus_topics)")
    p_config_set = sub_config.add_parser("set", help="Set a config value by dot path")
    p_config_set.add_argument("key", help="Dot-path key (example: queue_dir)")
    p_config_set.add_argument("value", help="Value (JSON for lists/objects, scalar otherwise)")
    p_config_unset = sub_config.add_parser("unset", help="Unset/remove a config key by dot path")
    p_config_unset.add_argument("key", help="Dot-path key to remove")

    return parser


def cmd_start(config_path: str) -> int:
    return run_daemon(config_path)


def cmd_run_once(config_path: str) -> int:
    run_once(config_path)
    return 0


def cmd_status(config_path: str) -> int:
    repo_cfg = load_repo_config(config_path)
    current_head = get_head_sha(repo_cfg.repo_root)
    st, _, _ = load_state(state_path(repo_cfg.shipnote_dir), fallback_last_sha=current_head)
    ledger = st.get("content_ledger", {})
    counts = ledger.get("category_counts_this_week", {})
    daemon = read_daemon_status(repo_cfg.shipnote_dir)
    daemon_line = "stopped"
    if daemon:
        pid = daemon.get("pid")
        started_at = str(daemon.get("started_at", ""))
        if isinstance(pid, int) and is_pid_alive(pid):
            uptime = uptime_seconds(started_at)
            daemon_line = f"running (pid={pid}, uptime_seconds={uptime if uptime is not None else 'unknown'})"
        else:
            daemon_line = "stopped (stale status file detected)"

    print(f"repo: {repo_cfg.repo_root}")
    print(f"daemon: {daemon_line}")
    print(f"last_commit_sha: {st.get('last_commit_sha')}")
    print(f"queue_counter: {st.get('queue_counter')}")
    print(f"processed_commits: {len(st.get('processed_commits', []))}")
    print(f"content_balance_week: {counts}")
    print(f"last_run_timestamp: {st.get('last_run_timestamp')}")
    return 0


def cmd_reset(config_path: str) -> int:
    repo_cfg = load_repo_config(config_path)
    current_head = get_head_sha(repo_cfg.repo_root)
    lock_path = repo_cfg.shipnote_dir / "runtime.lock"
    with exclusive_lock(lock_path):
        reset_state(state_path(repo_cfg.shipnote_dir), last_commit_sha=current_head)
    print("State reset complete.")
    return 0


def cmd_check(config_path: str) -> int:
    repo_cfg = load_repo_config(config_path)
    secrets = load_secrets(required=True)
    ensure_git_repo(repo_cfg.repo_root)
    templates = load_templates(repo_cfg.template_dir)
    missing_standard = missing_standard_templates(templates)

    print(f"config: OK ({Path(config_path).expanduser().resolve()})")
    print(f"git_repo: OK ({repo_cfg.repo_root})")
    print(f"branch: {get_branch_name(repo_cfg.repo_root)}")
    print(f"secrets: OK ({secrets.secrets_path})")
    if secrets.permissions_ok:
        print("secrets_permissions: OK (0o600)")
    else:
        print(f"secrets_permissions: WARN ({secrets.mode_octal}) expected 0o600")
    print(f"axis_model: {os.getenv(AXIS_MODEL_KEY, 'not set (axis-core default applies)')}")
    print(f"templates: OK ({len(templates)} files)")
    if missing_standard:
        print(f"templates_standard: WARN (missing: {', '.join(missing_standard)})")
    else:
        print("templates_standard: OK")
    return 0


def cmd_ask(config_path: str, question: str) -> int:
    print(answer_question(config_path, question))
    return 0


def cmd_chat(config_path: str) -> int:
    return run_chat(config_path)


def cmd_config(args: argparse.Namespace) -> int:
    if args.config_command == "list":
        print(list_config_text(args.config))
        return 0
    if args.config_command == "get":
        value = get_config_value(args.config, args.key)
        if isinstance(value, bool):
            print("true" if value else "false")
        elif isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2, ensure_ascii=True))
        else:
            print(value)
        return 0
    if args.config_command == "set":
        set_config_value(args.config, args.key, args.value)
        print(f"updated: {args.key}")
        return 0
    if args.config_command == "unset":
        unset_config_value(args.config, args.key)
        print(f"removed: {args.key}")
        return 0
    raise ShipnoteError(f"Unknown config subcommand: {args.config_command}")


def _bootstrap_from_args(args: argparse.Namespace) -> Path:
    result = bootstrap_repo(
        repo_path=Path(args.repo),
        project_name=args.project_name,
        project_description=args.project_description,
        voice_description=args.voice_description,
        poll_interval_seconds=args.poll_interval,
        force=bool(args.force),
        init_git=bool(args.init_git),
    )
    if result.git_initialized:
        print("git: initialized repository")
    if result.created_config:
        print(f"config: created ({result.config_path})")
    elif result.updated_config:
        print(f"config: updated ({result.config_path})")
    else:
        print(f"config: unchanged ({result.config_path})")
    print(f"templates_written: {result.template_count_written}")
    return result.config_path


def cmd_init(args: argparse.Namespace) -> int:
    config_path = _bootstrap_from_args(args)
    print(f"next: shipnote check --config {config_path}")
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    config_path = _bootstrap_from_args(args)
    cmd_check(str(config_path))
    print("launch: starting daemon loop (Ctrl+C to stop)")
    return run_daemon(str(config_path))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "start":
            return cmd_start(args.config)
        if args.command == "run-once":
            return cmd_run_once(args.config)
        if args.command == "status":
            return cmd_status(args.config)
        if args.command == "reset":
            return cmd_reset(args.config)
        if args.command == "check":
            return cmd_check(args.config)
        if args.command == "ask":
            return cmd_ask(args.config, args.question)
        if args.command == "chat":
            return cmd_chat(args.config)
        if args.command == "config":
            return cmd_config(args)
        if args.command == "init":
            return cmd_init(args)
        if args.command == "launch":
            return cmd_launch(args)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except ShipnoteError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
