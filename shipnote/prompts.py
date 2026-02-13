"""Prompt composition helpers."""

from __future__ import annotations

from .config_loader import RepoConfig


def _csv(values: list[str]) -> str:
    return ", ".join(values)


def build_generation_system_prompt(repo_cfg: RepoConfig) -> str:
    """Build the generation system prompt from config policy fields."""
    focus_topics = _csv(repo_cfg.content_policy.focus_topics)
    avoid_topics = _csv(repo_cfg.content_policy.avoid_topics)
    return (
        "You are Shipnote, a content generation agent for a developer sharing work publicly on Twitter/X.\n\n"
        "Generate tweet-ready drafts from sanitized commit context.\n\n"
        "Hard constraints:\n"
        "- Hook -> Context -> Value -> Payoff (punchline at end)\n"
        "- Single tweets must remain under 280 chars\n"
        "- Threads max 7 tweets and first tweet must stand alone\n"
        f"- Stay inside focus topics: {focus_topics}\n"
        f"- Never include off-topic content: {avoid_topics}\n"
        "- Keep tone technical but accessible, direct, and specific.\n"
    )
