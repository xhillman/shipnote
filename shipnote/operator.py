"""Operator ask/chat interfaces."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from axis_core import Agent, Capability, RetryPolicy, Timeouts, tool

from .axis_runtime import quiet_axis_logs
from .config_loader import AXIS_MODEL_KEY, load_repo_config
from .git_cli import get_head_sha
from .state_manager import load_state, state_path


def _list_markdown_files(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(path.glob("*.md"))


def _safe_md_filename(name: str) -> str:
    stripped = name.strip()
    if not stripped.endswith(".md"):
        raise ValueError("filename must end with .md")
    if "/" in stripped or "\\" in stripped or ".." in stripped:
        raise ValueError("filename must be a simple markdown filename in queue/templates")
    return stripped


def _fallback_answer(config_path: str, question: str) -> str:
    """Deterministic fallback response when agent run fails."""
    repo_cfg = load_repo_config(config_path)
    current_head = get_head_sha(repo_cfg.repo_root)
    state, _, _ = load_state(state_path(repo_cfg.shipnote_dir), fallback_last_sha=current_head)

    queue_files = _list_markdown_files(repo_cfg.queue_dir)
    template_files = _list_markdown_files(repo_cfg.template_dir)

    q = question.lower().strip()
    if not q:
        return "Ask about queue, state, templates, or commit tracking."
    if "queue" in q:
        preview = ", ".join(path.name for path in queue_files[:5]) or "none"
        return f"Queue has {len(queue_files)} draft file(s). First entries: {preview}."
    if "state" in q or "last commit" in q or "status" in q:
        return (
            f"last_commit_sha={state.get('last_commit_sha')}, "
            f"queue_counter={state.get('queue_counter')}, "
            f"processed_commits={len(state.get('processed_commits', []))}"
        )
    if "template" in q:
        names = ", ".join(path.name for path in template_files) or "none"
        return f"Templates available: {names}."
    if "edit" in q:
        return "Edit workflows are planned for Phase 9. Current interface is read-only Q&A."
    return (
        "Operator interface is online. Supported topics now: queue state, templates, "
        "and commit tracking."
    )


def _build_operator_agent(config_path: str) -> Agent:
    quiet_axis_logs()
    repo_cfg = load_repo_config(config_path)

    @tool(
        name="get_status",
        capabilities=[Capability.FILESYSTEM],
    )
    def get_status() -> dict[str, Any]:
        current_head = get_head_sha(repo_cfg.repo_root)
        state, _, _ = load_state(state_path(repo_cfg.shipnote_dir), fallback_last_sha=current_head)
        ledger = state.get("content_ledger", {})
        return {
            "repo": str(repo_cfg.repo_root),
            "last_commit_sha": state.get("last_commit_sha"),
            "queue_counter": state.get("queue_counter"),
            "processed_commits": len(state.get("processed_commits", [])),
            "content_balance_week": ledger.get("category_counts_this_week", {}),
            "saveable_this_week": ledger.get("saveable_this_week", 0),
            "week_start": ledger.get("week_start"),
            "last_run_timestamp": state.get("last_run_timestamp"),
        }

    @tool(
        name="list_queue",
        capabilities=[Capability.FILESYSTEM],
    )
    def list_queue(limit: int = 20) -> list[str]:
        files = _list_markdown_files(repo_cfg.queue_dir)
        if limit < 1:
            return []
        return [path.name for path in files[:limit]]

    @tool(
        name="read_draft",
        capabilities=[Capability.FILESYSTEM],
    )
    def read_draft(filename: str) -> str:
        safe = _safe_md_filename(filename)
        path = repo_cfg.queue_dir / safe
        if not path.exists():
            raise ValueError(f"draft not found: {safe}")
        return path.read_text(encoding="utf-8")

    @tool(
        name="search_queue",
        capabilities=[Capability.FILESYSTEM],
    )
    def search_queue(pattern: str, limit: int = 10) -> list[str]:
        if limit < 1:
            return []
        regex = re.compile(pattern, flags=re.IGNORECASE)
        matches: list[str] = []
        for path in _list_markdown_files(repo_cfg.queue_dir):
            haystack = f"{path.name}\n{path.read_text(encoding='utf-8')}"
            if regex.search(haystack):
                matches.append(path.name)
            if len(matches) >= limit:
                break
        return matches

    @tool(
        name="list_templates",
        capabilities=[Capability.FILESYSTEM],
    )
    def list_templates() -> list[str]:
        return [path.name for path in _list_markdown_files(repo_cfg.template_dir)]

    @tool(
        name="read_template",
        capabilities=[Capability.FILESYSTEM],
    )
    def read_template(filename: str) -> str:
        safe = _safe_md_filename(filename)
        path = repo_cfg.template_dir / safe
        if not path.exists():
            raise ValueError(f"template not found: {safe}")
        return path.read_text(encoding="utf-8")

    model_name = os.getenv(AXIS_MODEL_KEY, "").strip()
    agent_kwargs: dict[str, Any] = {
        "system": (
            "You are Shipnote Operator Assistant. "
            "Use tools to answer questions about queue state, draft content, templates, "
            "and strategy. Ground claims in tool outputs. Keep responses concise and practical."
        ),
        "tools": [get_status, list_queue, read_draft, search_queue, list_templates, read_template],
        "planner": "sequential",
        "telemetry": False,
        "verbose": False,
        "retry": RetryPolicy(
            max_attempts=2,
            backoff="fixed",
            initial_delay=1.0,
            max_delay=2.0,
            jitter=False,
        ),
        "timeouts": Timeouts(act=45.0, total=90.0),
    }
    if model_name:
        agent_kwargs["model"] = model_name
    return Agent(**agent_kwargs)


def answer_question(config_path: str, question: str) -> str:
    """Answer Shipnote operator questions using axis-core agent with fallback."""
    if not question.strip():
        return "Ask about queue, state, templates, commits, or draft edits."
    try:
        agent = _build_operator_agent(config_path)
        result = agent.run(question)
        if result.success and result.output_raw:
            return result.output_raw.strip()
        return _fallback_answer(config_path, question)
    except Exception:
        return _fallback_answer(config_path, question)


def run_chat(config_path: str) -> int:
    """Interactive operator chat loop."""
    try:
        agent = _build_operator_agent(config_path)
        session = agent.session()
    except Exception:
        agent = None
        session = None

    print("Shipnote chat started. Type 'exit' or 'quit' to end.")
    while True:
        try:
            prompt = input("shipnote> ").strip()
        except EOFError:
            print()
            return 0
        if prompt.lower() in {"exit", "quit"}:
            return 0
        if session is not None:
            try:
                result = session.run(prompt)
                answer = (result.output_raw or "").strip()
                if not answer:
                    answer = _fallback_answer(config_path, prompt)
            except Exception:
                answer = _fallback_answer(config_path, prompt)
        else:
            answer = _fallback_answer(config_path, prompt)
        print(answer)
