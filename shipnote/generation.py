"""axis-core generation engine."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from axis_core import Agent, RetryPolicy, Timeouts

from .axis_runtime import quiet_axis_logs
from .config_loader import AXIS_MODEL_KEY, RepoConfig
from .template_loader import TemplateDocument

ALLOWED_CATEGORIES = {
    "AI-Curious Builder",
    "Autonomy-Seeking Professional",
    "Systems-Minded Self-Improver",
    "cross-group",
}
ALLOWED_SUGGESTED_TIMES = {
    "weekday_morning",
    "weekday_afternoon",
    "weekday_evening",
    "weekend_afternoon",
}
ALLOWED_SIGNALS = {
    "like",
    "reply",
    "repost",
    "quote_tweet",
    "dwell_time",
    "profile_click",
    "copy_link",
    "dm_share",
}

SYSTEM_PROMPT = """You are Shipnote, a content generation agent for a developer who builds in public on Twitter/X.

Generate tweet-ready drafts from sanitized commit context.

Hard constraints:
- Hook -> Context -> Value -> Payoff (punchline at end)
- Single tweets must remain under 280 chars
- Threads max 7 tweets and first tweet must stand alone
- Stay inside niche: AI agents, building in public, automation, indie hacking, systems thinking
- Never include off-topic content (politics, sports, crypto)
- Keep tone technical but accessible, direct, and specific.
"""


def _build_user_prompt(
    repo_cfg: RepoConfig,
    context: dict[str, Any],
    templates: dict[str, TemplateDocument],
    max_drafts_per_commit: int,
) -> str:
    template_sections: list[str] = []
    for name, template in sorted(templates.items()):
        template_sections.append(f"### Template: {name}\n{template.raw}")

    return (
        "## Project Identity\n\n"
        f"project_name: {repo_cfg.project_name}\n"
        f"project_description: {repo_cfg.project_description}\n"
        f"voice_description: {repo_cfg.voice_description}\n\n"
        "## Context\n\n"
        f"{json.dumps(context, indent=2, ensure_ascii=True)}\n\n"
        "## Available Templates\n\n"
        + "\n\n".join(template_sections)
        + "\n\n## Instructions\n\n"
        f"Select 1-{max_drafts_per_commit} templates when appropriate and return JSON only.\n\n"
        "Return shape:\n"
        "{\n"
        '  "drafts": [\n'
        "    {\n"
        '      "template_type": "authority",\n'
        '      "content_category": "AI-Curious Builder",\n'
        '      "suggested_time": "weekday_morning",\n'
        '      "target_signals": ["dwell_time", "profile_click"],\n'
        '      "is_thread": false,\n'
        '      "content": "tweet text"\n'
        "    }\n"
        "  ],\n"
        '  "skip_reason": "optional"\n'
        "}\n"
    )


def _extract_json_object(text: str) -> str:
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")

    brace_count = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        char = text[idx]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                return text[start : idx + 1]
    raise ValueError("No complete JSON object found in model output")


def _validate_and_normalize_drafts(payload: dict[str, Any], max_drafts: int) -> dict[str, Any]:
    drafts_raw = payload.get("drafts", [])
    if not isinstance(drafts_raw, list):
        raise ValueError("`drafts` must be a list")

    normalized: list[dict[str, Any]] = []
    for item in drafts_raw[:max_drafts]:
        if not isinstance(item, dict):
            continue
        template_type = str(item.get("template_type", "")).strip()
        content_category = str(item.get("content_category", "")).strip()
        suggested_time = str(item.get("suggested_time", "")).strip()
        target_signals = item.get("target_signals", [])
        is_thread = bool(item.get("is_thread", False))
        content = str(item.get("content", "")).strip()

        if not template_type or not content:
            continue
        if content_category not in ALLOWED_CATEGORIES:
            continue
        if suggested_time not in ALLOWED_SUGGESTED_TIMES:
            continue
        if not isinstance(target_signals, list):
            continue
        filtered_signals = [s for s in target_signals if isinstance(s, str) and s in ALLOWED_SIGNALS]
        if len(filtered_signals) < 2:
            continue

        normalized.append(
            {
                "template_type": template_type,
                "content_category": content_category,
                "suggested_time": suggested_time,
                "target_signals": filtered_signals[:4],
                "is_thread": is_thread,
                "content": content,
            }
        )

    skip_reason = payload.get("skip_reason")
    if skip_reason is None:
        skip_reason = ""

    return {
        "drafts": normalized,
        "skip_reason": str(skip_reason).strip(),
    }


def generate_drafts(
    *,
    repo_cfg: RepoConfig,
    context: dict[str, Any],
    templates: dict[str, TemplateDocument],
    max_drafts: int,
) -> dict[str, Any]:
    """Generate draft variants using axis-core Agent."""
    quiet_axis_logs()
    if max_drafts < 1:
        return {"drafts": [], "skip_reason": "max_drafts must be >= 1"}

    model_name = os.getenv(AXIS_MODEL_KEY, "").strip()
    agent_kwargs: dict[str, Any] = {
        "system": SYSTEM_PROMPT,
        "planner": "sequential",
        "telemetry": False,
        "verbose": False,
        "retry": RetryPolicy(
            max_attempts=2,
            backoff="fixed",
            initial_delay=5.0,
            max_delay=5.0,
            jitter=False,
        ),
        "timeouts": Timeouts(act=60.0, total=75.0),
    }
    if model_name:
        agent_kwargs["model"] = model_name

    agent = Agent(**agent_kwargs)
    prompt = _build_user_prompt(repo_cfg, context, templates, max_drafts)
    result = agent.run(prompt)
    if not result.success:
        message = str(result.error) if result.error else "unknown model failure"
        raise RuntimeError(f"generation failed: {message}")

    raw_output = result.output_raw or ""
    json_text = _extract_json_object(raw_output)
    payload = json.loads(json_text)
    if not isinstance(payload, dict):
        raise ValueError("generation output root must be an object")
    return _validate_and_normalize_drafts(payload, max_drafts)
