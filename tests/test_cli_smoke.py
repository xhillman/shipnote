from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from shipnote.cli import main
from shipnote.config_loader import load_repo_config


class CliSmokeTests(unittest.TestCase):
    def _run_git(self, repo: Path, args: list[str]) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    def _run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = main(argv)
            except SystemExit as exc:
                code = int(exc.code) if isinstance(exc.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def test_init_config_set_and_status_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            self._run_git(repo, ["init", "-q"])

            previous_cwd = Path.cwd()
            try:
                os.chdir(repo)
                code, out, err = self._run_cli(["init"])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(code, 0, msg=err)
            self.assertIn("config:", out)
            config_path = repo / ".shipnote" / "config.yaml"
            self.assertTrue(config_path.exists())

            code, _, err = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "set",
                    "queue_dir",
                    ".shipnote/custom-queue",
                ]
            )
            self.assertEqual(code, 0, msg=err)

            code, _, err = self._run_cli(
                [
                    "config",
                    "--config",
                    str(config_path),
                    "set",
                    "content_policy.focus_topics",
                    '["python tooling"]',
                ]
            )
            self.assertEqual(code, 0, msg=err)
            cfg = load_repo_config(str(config_path))
            self.assertEqual(cfg.content_policy.focus_topics, ["python tooling"])
            self.assertEqual(cfg.queue_dir, (repo / ".shipnote/custom-queue").resolve())

            code, out, err = self._run_cli(["status", "--config", str(config_path)])
            self.assertEqual(code, 0, msg=err)
            self.assertIn("repo:", out)
            self.assertIn("queue_counter:", out)

    def test_status_auto_discovers_repo_config_from_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            self._run_git(repo, ["init", "-q"])

            previous_cwd = Path.cwd()
            try:
                os.chdir(repo)
                code, _, err = self._run_cli(["init"])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(code, 0, msg=err)

            nested = repo / "src" / "module"
            nested.mkdir(parents=True, exist_ok=True)
            previous_cwd = Path.cwd()
            try:
                os.chdir(nested)
                code, out, err = self._run_cli(["status"])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(code, 0, msg=err)
            self.assertIn(f"repo: {repo.resolve()}", out)


if __name__ == "__main__":
    unittest.main()
