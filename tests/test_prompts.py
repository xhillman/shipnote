from __future__ import annotations

import unittest
from pathlib import Path

from shipnote.config_loader import (
    ContentBalanceConfig,
    ContentPolicyConfig,
    ContextConfig,
    RepoConfig,
    SkipPatternsConfig,
)
from shipnote.prompts import build_generation_system_prompt


class PromptTests(unittest.TestCase):
    def test_build_generation_system_prompt_includes_configured_policy(self) -> None:
        root = Path("/tmp/shipnote")
        cfg = RepoConfig(
            config_path=root / ".shipnote" / "config.yaml",
            repo_root=root,
            shipnote_dir=root / ".shipnote",
            project_name="Shipnote",
            project_description="Draft generator",
            voice_description="Direct",
            poll_interval_seconds=60,
            max_drafts_per_commit=3,
            lookback_commits=10,
            template_dir=root / ".shipnote" / "templates",
            queue_dir=root / ".shipnote" / "queue",
            archive_dir=root / ".shipnote" / "archive",
            skip_patterns=SkipPatternsConfig(messages=[], files_only=[], min_meaningful_files=1),
            content_balance=ContentBalanceConfig(authority=30, translation=25, personal=25, growth=20),
            secret_patterns=[],
            raw_config={},
            context=ContextConfig(additional_files=[".shipnote/context.md"], max_total_chars=12000),
            content_policy=ContentPolicyConfig(
                focus_topics=["python tooling", "developer systems"],
                avoid_topics=["politics", "sports"],
                engagement_reminder="Engage where your users already discuss this topic.",
            ),
        )

        prompt = build_generation_system_prompt(cfg)

        self.assertIn("python tooling, developer systems", prompt)
        self.assertIn("politics, sports", prompt)
        self.assertIn("Single tweets must remain under 280 chars", prompt)
        self.assertIn("Threads max 7 tweets", prompt)


if __name__ == "__main__":
    unittest.main()
