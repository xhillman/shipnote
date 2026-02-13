from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from shipnote.config_loader import load_repo_config
from shipnote.errors import ShipnoteConfigError


def _run(repo: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write_config(repo: Path, body: str) -> Path:
    cfg_dir = repo / ".shipnote"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _base_config_text() -> str:
    return """
project_name: "Demo"
project_description: "Demo description"
voice_description: "Direct and technical"

poll_interval_seconds: 60
max_drafts_per_commit: 3
lookback_commits: 10

template_dir: ".shipnote/templates"
queue_dir: ".shipnote/queue"
archive_dir: ".shipnote/archive"

context:
  additional_files:
    - ".shipnote/context.md"
    - ".shipnote/notes.txt"
  max_total_chars: 12000

content_policy:
  focus_topics:
    - "software engineering"
    - "developer tooling"
  avoid_topics:
    - "politics"
    - "sports"
  engagement_reminder: "Engage in relevant community discussions before and after posting."

skip_patterns:
  messages:
    - "^wip"
  files_only:
    - "*.lock"
  min_meaningful_files: 1

content_balance:
  authority: 30
  translation: 25
  personal: 25
  growth: 20

secret_patterns:
  - "(sk-[a-zA-Z0-9]{20,})"
""".strip()


class ConfigLoaderTests(unittest.TestCase):
    def test_load_repo_config_parses_context_and_content_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            cfg = _write_config(repo, _base_config_text())

            loaded = load_repo_config(str(cfg))

            self.assertEqual(loaded.context.additional_files, [".shipnote/context.md", ".shipnote/notes.txt"])
            self.assertEqual(loaded.context.max_total_chars, 12000)
            self.assertEqual(loaded.content_policy.focus_topics, ["software engineering", "developer tooling"])
            self.assertEqual(loaded.content_policy.avoid_topics, ["politics", "sports"])
            self.assertIn("community discussions", loaded.content_policy.engagement_reminder)

    def test_load_repo_config_rejects_invalid_context_max_total_chars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            cfg = _write_config(repo, _base_config_text().replace("max_total_chars: 12000", "max_total_chars: 0"))

            with self.assertRaises(ShipnoteConfigError):
                load_repo_config(str(cfg))

    def test_load_repo_config_rejects_empty_focus_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            cfg = _write_config(
                repo,
                _base_config_text().replace(
                    'focus_topics:\n    - "software engineering"\n    - "developer tooling"',
                    "focus_topics: []",
                ),
            )

            with self.assertRaises(ShipnoteConfigError):
                load_repo_config(str(cfg))


if __name__ == "__main__":
    unittest.main()
