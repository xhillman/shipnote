from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from shipnote.config_loader import ContentBalanceConfig, RepoConfig, SkipPatternsConfig
from shipnote.git_cli import CommitInfo
from shipnote.queue_writer import write_drafts


class QueueWriterTests(unittest.TestCase):
    def _repo_cfg(self, root: Path) -> RepoConfig:
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
        )

    def test_writes_queue_file_and_updates_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._repo_cfg(root)
            cfg.queue_dir.mkdir(parents=True, exist_ok=True)

            state = {
                "queue_counter": 0,
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
                },
            }

            drafts = [
                {
                    "template_type": "authority",
                    "content_category": "AI-Curious Builder",
                    "suggested_time": "weekday_morning",
                    "target_signals": ["dwell_time", "profile_click"],
                    "is_thread": False,
                    "content": "First line",
                }
            ]
            commit = CommitInfo(
                sha="abc1234",
                message='Add "important" thing',
                author="Tester",
                date="2026-02-13 00:00:00 +0000",
            )
            paths = write_drafts(drafts=drafts, state=state, repo_cfg=cfg, commit=commit)

            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].exists())
            content = paths[0].read_text(encoding="utf-8")
            self.assertIn('commit_message: "Add \\"important\\" thing"', content)
            self.assertIn("engagement_reminder:", content)
            self.assertEqual(state["queue_counter"], 1)
            self.assertEqual(state["content_ledger"]["category_counts_this_week"]["authority"], 1)


if __name__ == "__main__":
    unittest.main()

