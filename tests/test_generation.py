from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shipnote.config_loader import (
    ContentBalanceConfig,
    ContentPolicyConfig,
    ContextConfig,
    RepoConfig,
    SkipPatternsConfig,
    TemplatePreferencesConfig,
)
from shipnote.generation import generate_drafts


def _repo_cfg(*, template_preferences: TemplatePreferencesConfig | None = None) -> RepoConfig:
    root = Path("/tmp/shipnote")
    prefs = template_preferences or TemplatePreferencesConfig(
        content_category_default_by_template={
            "authority": "AI-Curious Builder",
            "translation": "cross-group",
            "personal": "Autonomy-Seeking Professional",
            "growth": "Systems-Minded Self-Improver",
            "thread": "AI-Curious Builder",
            "weekly_wrapup": "cross-group",
        },
        is_thread_eligible_by_template={
            "authority": False,
            "translation": False,
            "personal": False,
            "growth": False,
            "thread": True,
            "weekly_wrapup": True,
        },
    )
    return RepoConfig(
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
            focus_topics=["python tooling"],
            avoid_topics=["politics", "sports"],
            engagement_reminder="Engage in relevant places.",
        ),
        template_preferences=prefs,
    )


class GenerationTests(unittest.TestCase):
    @patch("shipnote.generation.Timeouts")
    @patch("shipnote.generation.RetryPolicy")
    @patch("shipnote.generation.Agent")
    @patch("shipnote.generation.build_generation_system_prompt")
    def test_generate_drafts_uses_centralized_system_prompt(
        self,
        mock_build_prompt: MagicMock,
        mock_agent_cls: MagicMock,
        mock_retry_policy: MagicMock,
        mock_timeouts: MagicMock,
    ) -> None:
        repo_cfg = _repo_cfg()
        mock_build_prompt.return_value = "SYSTEM_FROM_BUILDER"
        mock_retry_policy.return_value = object()
        mock_timeouts.return_value = object()

        agent = MagicMock()
        agent.run.return_value = SimpleNamespace(
            success=True,
            output_raw=(
                '{"drafts":[{"template_type":"authority","content_category":"AI-Curious Builder",'
                '"suggested_time":"weekday_morning","target_signals":["dwell_time","profile_click"],'
                '"is_thread":false,"content":"A useful draft"}]}'
            ),
            error=None,
        )
        mock_agent_cls.return_value = agent

        result = generate_drafts(
            repo_cfg=repo_cfg,
            context={},
            templates={},
            max_drafts=1,
        )

        self.assertEqual(len(result["drafts"]), 1)
        mock_build_prompt.assert_called_once_with(repo_cfg)
        self.assertEqual(mock_agent_cls.call_args.kwargs["system"], "SYSTEM_FROM_BUILDER")

    @patch("shipnote.generation.Timeouts")
    @patch("shipnote.generation.RetryPolicy")
    @patch("shipnote.generation.Agent")
    @patch("shipnote.generation.build_generation_system_prompt")
    def test_generate_drafts_filters_ineligible_thread_drafts(
        self,
        mock_build_prompt: MagicMock,
        mock_agent_cls: MagicMock,
        mock_retry_policy: MagicMock,
        mock_timeouts: MagicMock,
    ) -> None:
        repo_cfg = _repo_cfg(
            template_preferences=TemplatePreferencesConfig(
                content_category_default_by_template={"authority": "AI-Curious Builder"},
                is_thread_eligible_by_template={"authority": False},
            )
        )
        mock_build_prompt.return_value = "SYSTEM_FROM_BUILDER"
        mock_retry_policy.return_value = object()
        mock_timeouts.return_value = object()

        agent = MagicMock()
        agent.run.return_value = SimpleNamespace(
            success=True,
            output_raw=(
                '{"drafts":[{"template_type":"authority","content_category":"AI-Curious Builder",'
                '"suggested_time":"weekday_morning","target_signals":["dwell_time","profile_click"],'
                '"is_thread":true,"content":"A thread that should be dropped"}]}'
            ),
            error=None,
        )
        mock_agent_cls.return_value = agent

        result = generate_drafts(
            repo_cfg=repo_cfg,
            context={},
            templates={},
            max_drafts=1,
        )

        self.assertEqual(result["drafts"], [])

    @patch("shipnote.generation.Timeouts")
    @patch("shipnote.generation.RetryPolicy")
    @patch("shipnote.generation.Agent")
    @patch("shipnote.generation.build_generation_system_prompt")
    def test_generate_drafts_keeps_eligible_thread_drafts(
        self,
        mock_build_prompt: MagicMock,
        mock_agent_cls: MagicMock,
        mock_retry_policy: MagicMock,
        mock_timeouts: MagicMock,
    ) -> None:
        repo_cfg = _repo_cfg(
            template_preferences=TemplatePreferencesConfig(
                content_category_default_by_template={"thread": "AI-Curious Builder"},
                is_thread_eligible_by_template={"thread": True},
            )
        )
        mock_build_prompt.return_value = "SYSTEM_FROM_BUILDER"
        mock_retry_policy.return_value = object()
        mock_timeouts.return_value = object()

        agent = MagicMock()
        agent.run.return_value = SimpleNamespace(
            success=True,
            output_raw=(
                '{"drafts":[{"template_type":"thread","content_category":"AI-Curious Builder",'
                '"suggested_time":"weekday_morning","target_signals":["dwell_time","profile_click"],'
                '"is_thread":true,"content":"A thread that should remain"}]}'
            ),
            error=None,
        )
        mock_agent_cls.return_value = agent

        result = generate_drafts(
            repo_cfg=repo_cfg,
            context={},
            templates={},
            max_drafts=1,
        )

        self.assertEqual(len(result["drafts"]), 1)
        self.assertTrue(result["drafts"][0]["is_thread"])


if __name__ == "__main__":
    unittest.main()
