from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from shipnote.cli import main
from shipnote.config_loader import load_repo_config
from shipnote.scaffold import bootstrap_repo


class CliConfigTests(unittest.TestCase):
    def _bootstrap(self, root: Path) -> Path:
        result = bootstrap_repo(repo_path=root, init_git=True)
        return result.config_path

    def _run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_config_set_updates_queue_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            config_path = self._bootstrap(repo)

            code, _, _ = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "set",
                    "queue_dir",
                    ".shipnote/custom-queue",
                ]
            )

            self.assertEqual(code, 0)
            loaded = load_repo_config(str(config_path))
            self.assertEqual(loaded.queue_dir, (repo / ".shipnote/custom-queue").resolve())

    def test_config_set_invalid_value_does_not_modify_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            config_path = self._bootstrap(repo)
            original = config_path.read_text(encoding="utf-8")

            code, _, err = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "set",
                    "poll_interval_seconds",
                    "0",
                ]
            )

            self.assertEqual(code, 1)
            self.assertIn("must be >=", err)
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)

    def test_config_get_returns_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            config_path = self._bootstrap(repo)

            code, out, _ = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "get",
                    "queue_dir",
                ]
            )

            self.assertEqual(code, 0)
            self.assertIn(".shipnote/queue", out)

    def test_config_get_nested_list_returns_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            config_path = self._bootstrap(repo)

            code, out, _ = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "get",
                    "content_policy.avoid_topics",
                ]
            )

            self.assertEqual(code, 0)
            self.assertIn("[", out)
            self.assertIn("politics", out)

    def test_config_set_parses_json_list_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            config_path = self._bootstrap(repo)

            code, _, _ = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "set",
                    "content_policy.focus_topics",
                    '["python tooling","agent systems"]',
                ]
            )

            self.assertEqual(code, 0)
            loaded = load_repo_config(str(config_path))
            self.assertEqual(loaded.content_policy.focus_topics, ["python tooling", "agent systems"])

    def test_config_list_prints_current_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            config_path = self._bootstrap(repo)

            code, out, _ = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "list",
                ]
            )

            self.assertEqual(code, 0)
            self.assertIn("project_name:", out)
            self.assertIn("content_policy:", out)

    def test_config_unset_required_key_fails_and_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            config_path = self._bootstrap(repo)
            original = config_path.read_text(encoding="utf-8")

            code, _, err = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "unset",
                    "project_name",
                ]
            )

            self.assertEqual(code, 1)
            self.assertIn("project_name", err)
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
