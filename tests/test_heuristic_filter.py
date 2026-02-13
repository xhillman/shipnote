from __future__ import annotations

import unittest

from buildlog.config_loader import SkipPatternsConfig
from buildlog.heuristic_filter import should_keep_commit


class HeuristicFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = SkipPatternsConfig(
            messages=[r"^wip", r"^fix typo"],
            files_only=["*.lock", ".env*"],
            min_meaningful_files=1,
        )

    def test_skips_matching_message_pattern(self) -> None:
        keep, reason = should_keep_commit("wip save", ["src/main.py"], self.cfg)
        self.assertFalse(keep)
        self.assertIn("message matched", reason)

    def test_skips_when_only_ignored_files_changed(self) -> None:
        keep, reason = should_keep_commit("deps update", ["package.lock", ".env.local"], self.cfg)
        self.assertFalse(keep)
        self.assertIn("insufficient meaningful files", reason)

    def test_keeps_when_meaningful_files_present(self) -> None:
        keep, reason = should_keep_commit(
            "Refactor planner",
            ["src/planner.py", "package.lock"],
            self.cfg,
        )
        self.assertTrue(keep)
        self.assertIn("kept", reason)


if __name__ == "__main__":
    unittest.main()

