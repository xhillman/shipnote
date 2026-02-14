from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from shipnote.config_loader import (
    ContentBalanceConfig,
    ContentPolicyConfig,
    ContextConfig,
    RepoConfig,
    SkipPatternsConfig,
)
from shipnote.context_builder import build_context
from shipnote.errors import ShipnoteConfigError
from shipnote.git_cli import CommitInfo


def _repo_cfg(root: Path, *, additional_files: list[str], max_total_chars: int) -> RepoConfig:
    shipnote_dir = root / ".shipnote"
    return RepoConfig(
        config_path=shipnote_dir / "config.yaml",
        repo_root=root,
        shipnote_dir=shipnote_dir,
        project_name="Test",
        project_description="Test project",
        voice_description="Direct",
        poll_interval_seconds=60,
        max_drafts_per_commit=3,
        lookback_commits=10,
        template_dir=shipnote_dir / "templates",
        queue_dir=shipnote_dir / "queue",
        archive_dir=shipnote_dir / "archive",
        skip_patterns=SkipPatternsConfig(messages=[], files_only=[], min_meaningful_files=1),
        content_balance=ContentBalanceConfig(authority=30, translation=25, personal=25, growth=20),
        secret_patterns=[],
        raw_config={},
        context=ContextConfig(additional_files=additional_files, max_total_chars=max_total_chars),
        content_policy=ContentPolicyConfig(
            focus_topics=["software engineering"],
            avoid_topics=["politics", "sports", "crypto"],
            engagement_reminder="Engage in relevant community discussions before and after posting.",
        ),
    )


def _commit() -> CommitInfo:
    return CommitInfo(
        sha="abc1234",
        message="Add safe context loading",
        author="Tester",
        date="2026-02-13 00:00:00 +0000",
    )


def _state() -> dict[str, object]:
    return {
        "content_ledger": {
            "recent_drafts": [],
            "category_counts_this_week": {
                "authority": 0,
                "translation": 0,
                "personal": 0,
                "growth": 0,
            },
            "saveable_this_week": 0,
            "week_start": "2026-02-09",
        }
    }


class ContextBuilderTests(unittest.TestCase):
    def test_includes_additional_notes_from_allowlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shipnote_dir = root / ".shipnote"
            shipnote_dir.mkdir(parents=True, exist_ok=True)
            (shipnote_dir / "context.md").write_text("alpha", encoding="utf-8")
            (shipnote_dir / "notes.txt").write_text("beta", encoding="utf-8")
            cfg = _repo_cfg(
                root,
                additional_files=[".shipnote/context.md", ".shipnote/notes.txt"],
                max_total_chars=100,
            )

            payload = build_context(
                repo_cfg=cfg,
                commit=_commit(),
                files_changed=["shipnote/context_builder.py"],
                sanitized_diff="+context",
                current_branch="main",
                recent_history=["one", "two"],
                state=_state(),
            )

            self.assertEqual(
                payload["additional_notes"],
                [
                    {"path": ".shipnote/context.md", "content": "alpha"},
                    {"path": ".shipnote/notes.txt", "content": "beta"},
                ],
            )

    def test_missing_additional_note_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shipnote_dir = root / ".shipnote"
            shipnote_dir.mkdir(parents=True, exist_ok=True)
            (shipnote_dir / "context.md").write_text("alpha", encoding="utf-8")
            cfg = _repo_cfg(
                root,
                additional_files=[".shipnote/context.md", ".shipnote/missing.md"],
                max_total_chars=100,
            )

            payload = build_context(
                repo_cfg=cfg,
                commit=_commit(),
                files_changed=["shipnote/context_builder.py"],
                sanitized_diff="+context",
                current_branch="main",
                recent_history=["one", "two"],
                state=_state(),
            )

            self.assertEqual(payload["additional_notes"], [{"path": ".shipnote/context.md", "content": "alpha"}])

    def test_rejects_additional_note_outside_dot_shipnote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _repo_cfg(
                root,
                additional_files=["docs/context.md"],
                max_total_chars=100,
            )

            with self.assertRaises(ShipnoteConfigError):
                build_context(
                    repo_cfg=cfg,
                    commit=_commit(),
                    files_changed=["shipnote/context_builder.py"],
                    sanitized_diff="+context",
                    current_branch="main",
                    recent_history=["one", "two"],
                    state=_state(),
                )

    def test_rejects_additional_note_with_non_allowlisted_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shipnote_dir = root / ".shipnote"
            shipnote_dir.mkdir(parents=True, exist_ok=True)
            (shipnote_dir / "context.yaml").write_text("alpha", encoding="utf-8")
            cfg = _repo_cfg(
                root,
                additional_files=[".shipnote/context.yaml"],
                max_total_chars=100,
            )

            with self.assertRaises(ShipnoteConfigError):
                build_context(
                    repo_cfg=cfg,
                    commit=_commit(),
                    files_changed=["shipnote/context_builder.py"],
                    sanitized_diff="+context",
                    current_branch="main",
                    recent_history=["one", "two"],
                    state=_state(),
                )

    def test_truncates_additional_notes_to_max_total_chars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shipnote_dir = root / ".shipnote"
            shipnote_dir.mkdir(parents=True, exist_ok=True)
            (shipnote_dir / "a.md").write_text("abcdefgh", encoding="utf-8")
            (shipnote_dir / "b.txt").write_text("ijklmnop", encoding="utf-8")
            cfg = _repo_cfg(
                root,
                additional_files=[".shipnote/a.md", ".shipnote/b.txt"],
                max_total_chars=10,
            )

            payload = build_context(
                repo_cfg=cfg,
                commit=_commit(),
                files_changed=["shipnote/context_builder.py"],
                sanitized_diff="+context",
                current_branch="main",
                recent_history=["one", "two"],
                state=_state(),
            )

            self.assertEqual(payload["additional_notes"][0]["content"], "abcdefgh")
            self.assertEqual(payload["additional_notes"][1]["content"], "ij")
            total = sum(len(item["content"]) for item in payload["additional_notes"])
            self.assertEqual(total, 10)


if __name__ == "__main__":
    unittest.main()
