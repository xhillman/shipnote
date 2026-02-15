"""Prompt composition helpers."""

from __future__ import annotations

from .config_loader import RepoConfig


def _csv(values: list[str]) -> str:
    return ", ".join(values)


def _render_preference_map(values: dict[str, str]) -> str:
    return "\n".join(f"- {key} -> {value}" for key, value in sorted(values.items()))


def _render_bool_preference_map(values: dict[str, bool]) -> str:
    return "\n".join(
        f"- {key} -> {str(is_eligible).lower()}" for key, is_eligible in sorted(values.items())
    )


def build_generation_system_prompt(repo_cfg: RepoConfig) -> str:
    """Build the generation system prompt from config policy fields."""
    focus_topics = _csv(repo_cfg.content_policy.focus_topics)
    avoid_topics = _csv(repo_cfg.content_policy.avoid_topics)
    category_defaults = _render_preference_map(
        repo_cfg.template_preferences.content_category_default_by_template
    )
    thread_eligibility = _render_bool_preference_map(
        repo_cfg.template_preferences.is_thread_eligible_by_template
    )
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
        "\nTemplate preferences:\n"
        "content_category_default_by_template:\n"
        f"{category_defaults}\n"
        "is_thread_eligible_by_template:\n"
        f"{thread_eligibility}\n"
    )
