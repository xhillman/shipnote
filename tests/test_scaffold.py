from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from shipnote.errors import ShipnoteConfigError
from shipnote.scaffold import bootstrap_repo


def _run(repo: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


class ScaffoldTests(unittest.TestCase):
    def test_bootstrap_writes_config_and_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])

            result = bootstrap_repo(repo_path=repo, poll_interval_seconds=45)
            self.assertTrue(result.config_path.exists())
            self.assertTrue(result.created_config)
            self.assertGreaterEqual(result.template_count_written, 6)

            config_text = result.config_path.read_text(encoding="utf-8")
            self.assertIn("poll_interval_seconds: 45", config_text)
            self.assertIn('template_dir: ".shipnote/templates"', config_text)
            self.assertIn('queue_dir: ".shipnote/drafts"', config_text)
            self.assertNotIn("Builder-in-public", config_text)
            self.assertIn("context:", config_text)
            self.assertIn("additional_files:", config_text)
            self.assertIn("max_total_chars: 12000", config_text)
            self.assertIn("content_policy:", config_text)
            self.assertIn("focus_topics:", config_text)
            self.assertIn("avoid_topics:", config_text)
            self.assertIn("engagement_reminder:", config_text)
            self.assertTrue((repo / ".shipnote" / "drafts").exists())
            authority_text = (repo / ".shipnote" / "templates" / "authority.md").read_text(encoding="utf-8")
            self.assertNotIn("Building this in public", authority_text)

    def test_bootstrap_requires_git_without_init_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            with self.assertRaises(ShipnoteConfigError):
                bootstrap_repo(repo_path=repo, init_git=False)

    def test_bootstrap_can_initialize_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            result = bootstrap_repo(repo_path=repo, init_git=True)
            self.assertTrue(result.git_initialized)
            self.assertTrue((repo / ".git").exists())


if __name__ == "__main__":
    unittest.main()
