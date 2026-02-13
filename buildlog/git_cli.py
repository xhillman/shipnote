"""Read-only git helpers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import BuildLogGitError


@dataclass(frozen=True)
class CommitInfo:
    """Metadata for a single commit."""

    sha: str
    message: str
    author: str
    date: str


def _run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown git error"
        raise BuildLogGitError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout


def ensure_git_repo(repo_root: Path) -> None:
    """Validate that the path is inside a git work tree."""
    output = _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"]).strip().lower()
    if output != "true":
        raise BuildLogGitError(f"Path is not a git work tree: {repo_root}")


def get_head_sha(repo_root: Path) -> str | None:
    """Return HEAD commit SHA or None for empty repos."""
    try:
        return _run_git(repo_root, ["rev-parse", "HEAD"]).strip() or None
    except BuildLogGitError:
        return None


def get_branch_name(repo_root: Path) -> str:
    """Return current branch name.

    Handles unborn HEAD (repo initialized but no commits) by falling back to
    symbolic-ref and then a stable placeholder.
    """
    try:
        branch = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        if branch:
            return branch
    except BuildLogGitError:
        pass

    try:
        branch = _run_git(repo_root, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
        if branch:
            return branch
    except BuildLogGitError:
        pass

    return "unborn"


def commit_exists(repo_root: Path, sha: str) -> bool:
    """Return True if a commit object exists."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def commit_in_history(repo_root: Path, sha: str) -> bool:
    """Return True if commit is reachable from HEAD."""
    if not commit_exists(repo_root, sha):
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def list_recent_messages(repo_root: Path, lookback_commits: int) -> list[str]:
    """Return recent commit messages."""
    if lookback_commits < 1:
        return []
    output = _run_git(repo_root, ["log", "--format=%s", "-n", str(lookback_commits)])
    return [line.strip() for line in output.splitlines() if line.strip()]


def parse_log_lines(output: str) -> list[CommitInfo]:
    """Parse `%H|||%s|||%an|||%ai` lines into dicts."""
    commits: list[CommitInfo] = []
    for line in output.splitlines():
        parts = line.split("|||")
        if len(parts) != 4:
            continue
        sha, message, author, date = (part.strip() for part in parts)
        commits.append(CommitInfo(sha=sha, message=message, author=author, date=date))
    return commits


def list_new_commits(repo_root: Path, last_sha: str | None) -> list[CommitInfo]:
    """List new commits since last SHA, oldest first."""
    ensure_git_repo(repo_root)
    if not last_sha:
        output = _run_git(repo_root, ["log", "--format=%H|||%s|||%an|||%ai", "-n", "1"])
        return parse_log_lines(output)

    if not commit_in_history(repo_root, last_sha):
        raise BuildLogGitError(f"Last seen commit {last_sha} is not in current history.")

    output = _run_git(repo_root, ["log", "--reverse", "--format=%H|||%s|||%an|||%ai", f"{last_sha}..HEAD"])
    return parse_log_lines(output)


def get_commit_diff(repo_root: Path, sha: str) -> str:
    """Return commit diff text for a single commit."""
    try:
        return _run_git(repo_root, ["diff", f"{sha}^..{sha}"])
    except BuildLogGitError:
        # Handle root commits (no parent) safely.
        return _run_git(repo_root, ["show", "--format=", sha])


def get_commit_diff_stat(repo_root: Path, sha: str) -> str:
    """Return human-readable diff stat for a single commit."""
    try:
        return _run_git(repo_root, ["diff", "--stat", f"{sha}^..{sha}"])
    except BuildLogGitError:
        return _run_git(repo_root, ["show", "--format=", "--stat", sha])


def get_commit_files_changed(repo_root: Path, sha: str) -> list[str]:
    """Return changed files for a commit."""
    try:
        output = _run_git(repo_root, ["diff", "--name-only", f"{sha}^..{sha}"])
    except BuildLogGitError:
        output = _run_git(repo_root, ["show", "--format=", "--name-only", sha])
    return [line.strip() for line in output.splitlines() if line.strip()]


def commit_info_to_dict(commit: CommitInfo) -> dict[str, Any]:
    """Convert commit info dataclass to dict payload."""
    return {
        "sha": commit.sha,
        "message": commit.message,
        "author": commit.author,
        "date": commit.date,
    }
