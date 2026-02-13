from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from buildlog.errors import BuildLogGitError
from buildlog.git_cli import get_branch_name, list_new_commits


def _run(repo: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


class GitCliTests(unittest.TestCase):
    def test_branch_name_on_unborn_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            branch = get_branch_name(repo)
            self.assertTrue(branch)

    def test_list_new_commits_detects_rewritten_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            _run(repo, ["init", "-q"])
            _run(repo, ["config", "user.email", "test@example.com"])
            _run(repo, ["config", "user.name", "Tester"])

            (repo / "a.txt").write_text("a\n", encoding="utf-8")
            _run(repo, ["add", "a.txt"])
            _run(repo, ["commit", "-m", "first"])
            first = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip()

            (repo / "a.txt").write_text("a\nb\n", encoding="utf-8")
            _run(repo, ["add", "a.txt"])
            _run(repo, ["commit", "-m", "second"])
            second = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip()

            _run(repo, ["reset", "--hard", first])
            (repo / "a.txt").write_text("a\nc\n", encoding="utf-8")
            _run(repo, ["add", "a.txt"])
            _run(repo, ["commit", "-m", "after-rewrite"])

            with self.assertRaises(BuildLogGitError):
                list_new_commits(repo, second)


if __name__ == "__main__":
    unittest.main()

