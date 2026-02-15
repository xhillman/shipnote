from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shipnote.cli import main
from shipnote.config_loader import load_repo_config
from shipnote.scaffold import bootstrap_repo


def _run(repo: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


class CliWizardTests(unittest.TestCase):
    def _run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = main(argv)
            except SystemExit as exc:
                code = int(exc.code) if isinstance(exc.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def test_setup_writes_global_defaults_from_wizard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults_path = root / ".shipnote" / "defaults.yaml"
            responses = [
                "75",
                "Calm and concise",
                "python tooling,release engineering",
                "politics,sports",
                "Engage with maintainers.",
            ]

            with patch("shipnote.cli.default_global_defaults_path", return_value=defaults_path):
                with patch("builtins.input", side_effect=responses):
                    code, out, err = self._run_cli(["setup"])

            self.assertEqual(code, 0, msg=err)
            self.assertIn("defaults: written", out)
            self.assertTrue(defaults_path.exists())
            text = defaults_path.read_text(encoding="utf-8")
            self.assertIn("poll_interval_seconds: 75", text)
            self.assertIn('voice_description: "Calm and concise"', text)
            self.assertIn('- "python tooling"', text)

    def test_init_uses_current_directory_and_global_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])

            defaults_path = root / ".shipnote" / "defaults.yaml"
            defaults_path.parent.mkdir(parents=True, exist_ok=True)
            defaults_path.write_text(
                "\n".join(
                    [
                        "poll_interval_seconds: 91",
                        'voice_description: "Voice from defaults"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            previous_cwd = Path.cwd()
            try:
                os.chdir(repo)
                with patch("shipnote.scaffold.default_global_defaults_path", return_value=defaults_path):
                    code, out, err = self._run_cli(["init"])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(code, 0, msg=err)
            self.assertIn("config: created", out)
            loaded = load_repo_config(str(repo / ".shipnote" / "config.yaml"))
            self.assertEqual(loaded.poll_interval_seconds, 91)
            self.assertEqual(loaded.voice_description, "Voice from defaults")

    def test_init_fails_outside_git_repo_with_actionable_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)

            previous_cwd = Path.cwd()
            try:
                os.chdir(repo)
                code, _, err = self._run_cli(["init"])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(code, 1)
            self.assertIn("git init", err)
            self.assertIn("shipnote init", err)

    def test_config_command_without_subcommand_runs_interactive_wizard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            bootstrap_repo(repo_path=repo, init_git=True)

            responses = [
                "120",
                "Voice updated in config wizard",
                "",
                "",
                "",
            ]
            previous_cwd = Path.cwd()
            try:
                os.chdir(repo)
                with patch("builtins.input", side_effect=responses):
                    code, out, err = self._run_cli(["config"])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(code, 0, msg=err)
            self.assertIn("config: updated", out)
            loaded = load_repo_config(str(repo / ".shipnote" / "config.yaml"))
            self.assertEqual(loaded.poll_interval_seconds, 120)
            self.assertEqual(loaded.voice_description, "Voice updated in config wizard")


if __name__ == "__main__":
    unittest.main()
