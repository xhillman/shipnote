"""Core run-once and daemon loop scaffold."""

from __future__ import annotations

import signal
import time
from pathlib import Path
from typing import Any

from .config_loader import RepoConfig, ensure_runtime_dirs, load_repo_config, load_secrets
from .context_builder import build_context
from .daemon_runtime import clear_daemon_status, write_daemon_status
from .errors import BuildLogGitError
from .git_cli import (
    CommitInfo,
    ensure_git_repo,
    get_branch_name,
    get_commit_diff,
    get_commit_diff_stat,
    get_commit_files_changed,
    get_head_sha,
    list_recent_messages,
    list_new_commits,
)
from .generation import generate_drafts
from .heuristic_filter import should_keep_commit
from .lockfile import exclusive_lock
from .logging_utils import LOGGER
from .queue_writer import write_drafts
from .secret_scanner import redact_diff
from .state_manager import load_state, save_state, state_path, utc_now
from .template_loader import load_templates, missing_standard_templates


def _update_processed_commits(state: dict[str, Any], sha: str) -> None:
    processed = [x for x in state.get("processed_commits", []) if x != sha]
    processed.append(sha)
    state["processed_commits"] = processed[-100:]


def _is_already_processed(state: dict[str, Any], sha: str) -> bool:
    processed = state.get("processed_commits", [])
    return isinstance(processed, list) and sha in processed


def _mark_commit_processed(st_path: Path, state: dict[str, Any], commit: CommitInfo) -> None:
    state["last_commit_sha"] = commit.sha
    state["last_run_timestamp"] = utc_now()
    _update_processed_commits(state, commit.sha)
    save_state(st_path, state)


def _runtime_lock_path(buildlog_dir: Path) -> Path:
    return buildlog_dir / "runtime.lock"


def _run_once_locked(repo_cfg: RepoConfig, *, require_secrets: bool = True) -> int:
    """Process commit discovery once and persist updated state (internal, locked)."""
    secrets_cfg = load_secrets(required=require_secrets)
    ensure_git_repo(repo_cfg.repo_root)
    if secrets_cfg.values and not secrets_cfg.permissions_ok:
        LOGGER.warn(
            f"Expected chmod 600 on {secrets_cfg.secrets_path}, found mode {secrets_cfg.mode_octal}"
        )

    head_sha = get_head_sha(repo_cfg.repo_root)
    if not head_sha:
        LOGGER.warn("Repository has no commits yet.")
        return 0

    st_path = state_path(repo_cfg.buildlog_dir)
    had_state_file = st_path.exists()
    state, recovered, rolled_over = load_state(st_path)
    if recovered:
        if had_state_file:
            LOGGER.warn("State file invalid. Initialized a fresh state snapshot.")
            # Corrupted state recovery policy: reset baseline to HEAD and continue next cycle.
            state["last_commit_sha"] = head_sha
            state["last_run_timestamp"] = utc_now()
            save_state(st_path, state)
            LOGGER.warn("Corrupted state recovery: baseline reset to current HEAD.")
            return 0
        LOGGER.info("State file not found. First-run mode enabled.")
    if rolled_over:
        LOGGER.info("Weekly content ledger rolled over to a new Monday window.")
    templates = load_templates(repo_cfg.template_dir)
    missing_standard = missing_standard_templates(templates)
    if missing_standard:
        LOGGER.warn(f"Missing standard templates: {', '.join(missing_standard)}")

    try:
        commits = list_new_commits(repo_cfg.repo_root, state.get("last_commit_sha"))
    except BuildLogGitError as exc:
        if "not in current history" in str(exc):
            LOGGER.warn("last_commit_sha not present in history; resetting baseline to current HEAD.")
            try:
                commits = list_new_commits(repo_cfg.repo_root, None)
            except BuildLogGitError as nested_exc:
                LOGGER.error(f"Git read failed: {nested_exc}")
                return 0
        else:
            LOGGER.error(f"Git read failed: {exc}")
            return 0

    if not commits:
        state["last_run_timestamp"] = utc_now()
        save_state(st_path, state)
        LOGGER.info("Poll cycle complete: 0 new commits.")
        return 0

    processed_count = 0
    kept_count = 0
    skipped_count = 0
    git_failed = False

    for commit in commits:
        if _is_already_processed(state, commit.sha):
            LOGGER.info(f"Skipping already-processed commit {commit.sha[:7]}.")
            state["last_commit_sha"] = commit.sha
            continue

        try:
            files_changed = get_commit_files_changed(repo_cfg.repo_root, commit.sha)
        except BuildLogGitError as exc:
            LOGGER.error(f"Git read failed for commit {commit.sha[:7]} file list: {exc}")
            git_failed = True
            break

        keep, reason = should_keep_commit(commit.message, files_changed, repo_cfg.skip_patterns)
        if not keep:
            LOGGER.info(f"Skipping commit {commit.sha[:7]}: {reason}")
            _mark_commit_processed(st_path, state, commit)
            processed_count += 1
            skipped_count += 1
            continue

        try:
            raw_diff = get_commit_diff(repo_cfg.repo_root, commit.sha)
            diff_stat = get_commit_diff_stat(repo_cfg.repo_root, commit.sha)
        except BuildLogGitError as exc:
            LOGGER.error(f"Git read failed for commit {commit.sha[:7]} diff: {exc}")
            git_failed = True
            break

        sanitized_diff, redaction_count = redact_diff(raw_diff, repo_cfg.secret_patterns)
        if redaction_count > 0:
            LOGGER.warn(
                f"Secret scanner redacted {redaction_count} match(es) in commit {commit.sha[:7]}."
            )

        try:
            current_branch = get_branch_name(repo_cfg.repo_root)
            recent_history = list_recent_messages(repo_cfg.repo_root, repo_cfg.lookback_commits)
        except BuildLogGitError as exc:
            LOGGER.error(f"Git read failed while building context for {commit.sha[:7]}: {exc}")
            git_failed = True
            break

        context = build_context(
            repo_cfg=repo_cfg,
            commit=commit,
            files_changed=files_changed,
            sanitized_diff=sanitized_diff,
            current_branch=current_branch,
            recent_history=recent_history,
            state=state,
        )

        LOGGER.info(f"Detected commit {commit.sha[:7]}: {commit.message}")
        if diff_stat.strip():
            first_line = diff_stat.strip().splitlines()[0]
            LOGGER.info(f"Diff stat ({commit.sha[:7]}): {first_line}")
        LOGGER.info(
            f"Context recommendation ({commit.sha[:7]}): "
            f"{context['content_balance']['recommendation']}"
        )
        LOGGER.info(
            "Prepared sanitized commit payload "
            f"{commit.sha[:7]} (diff_chars={len(sanitized_diff)}, templates={len(templates)})."
        )

        generation: dict[str, object] | None = None
        first_error: Exception | None = None
        for attempt in (1, 2):
            try:
                generation = generate_drafts(
                    repo_cfg=repo_cfg,
                    context=context,
                    templates=templates,
                    max_drafts=repo_cfg.max_drafts_per_commit,
                )
                break
            except Exception as exc:
                if attempt == 1:
                    first_error = exc
                    LOGGER.warn(
                        f"Generation attempt 1 failed for commit {commit.sha[:7]}: {exc}. Retrying in 5s."
                    )
                    time.sleep(5)
                    continue
                LOGGER.error(f"Generation failed for commit {commit.sha[:7]}: {exc}")
                if first_error is not None:
                    LOGGER.error(
                        f"Initial generation failure for commit {commit.sha[:7]}: {first_error}"
                    )

        if generation is None:
            _mark_commit_processed(st_path, state, commit)
            processed_count += 1
            kept_count += 1
            continue

        drafts = generation.get("drafts", [])
        if not isinstance(drafts, list) or not drafts:
            skip_reason = str(generation.get("skip_reason", "no drafts returned")).strip()
            LOGGER.info(f"No drafts for commit {commit.sha[:7]}: {skip_reason}")
            _mark_commit_processed(st_path, state, commit)
            processed_count += 1
            kept_count += 1
            continue

        try:
            written_paths = write_drafts(
                drafts=drafts,
                state=state,
                repo_cfg=repo_cfg,
                commit=commit,
            )
        except Exception as exc:
            LOGGER.error(f"Queue write failed for commit {commit.sha[:7]}: {exc}")
            # Persist counter/ledger progress if any write succeeded before failure.
            save_state(st_path, state)
            LOGGER.warn("Poll cycle ended early due to queue write error; commit will retry next cycle.")
            git_failed = True
            break
        for path in written_paths:
            LOGGER.info(f"Queued draft: {path.name}")

        _mark_commit_processed(st_path, state, commit)
        processed_count += 1
        kept_count += 1

    if processed_count == 0 and not git_failed:
        state["last_run_timestamp"] = utc_now()
        save_state(st_path, state)

    if git_failed:
        LOGGER.warn("Poll cycle ended early due to git error; remaining commits will retry next cycle.")

    LOGGER.info(
        "Poll cycle complete: "
        f"{processed_count} new commit(s), {kept_count} kept, {skipped_count} skipped."
    )
    return processed_count


def run_once(config_path: str, *, require_secrets: bool = True) -> int:
    """Process commit discovery once and persist updated state."""
    repo_cfg = load_repo_config(config_path)
    ensure_runtime_dirs(repo_cfg)
    lock_path = _runtime_lock_path(repo_cfg.buildlog_dir)
    with exclusive_lock(lock_path):
        return _run_once_locked(repo_cfg, require_secrets=require_secrets)


def run_daemon(config_path: str) -> int:
    """Run polling loop until interrupted."""
    repo_cfg = load_repo_config(config_path)
    ensure_runtime_dirs(repo_cfg)
    load_secrets(required=True)
    ensure_git_repo(repo_cfg.repo_root)
    lock_path = _runtime_lock_path(repo_cfg.buildlog_dir)

    LOGGER.info(
        f"Daemon start: repo={repo_cfg.repo_root} interval={repo_cfg.poll_interval_seconds}s"
    )
    write_daemon_status(repo_cfg.buildlog_dir, config_path=str(repo_cfg.config_path))

    stop_requested = {"value": False}

    def _handle_signal(signum: int, _frame: object) -> None:
        if not stop_requested["value"]:
            LOGGER.info(f"Shutdown signal received ({signum}). Finishing current cycle before exit.")
        stop_requested["value"] = True

    prev_int = signal.getsignal(signal.SIGINT)
    prev_term = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not stop_requested["value"]:
            with exclusive_lock(lock_path):
                _run_once_locked(repo_cfg, require_secrets=False)

            if stop_requested["value"]:
                break

            remaining = int(repo_cfg.poll_interval_seconds)
            while remaining > 0 and not stop_requested["value"]:
                time.sleep(1)
                remaining -= 1
    finally:
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)
        clear_daemon_status(repo_cfg.buildlog_dir)

    LOGGER.info("Daemon stopped gracefully.")
    return 0
