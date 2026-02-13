from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shipnote.state_manager import load_state, save_state


class StateManagerTests(unittest.TestCase):
    def test_week_rollover_resets_weekly_counters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            payload = {
                "last_commit_sha": "abc123",
                "queue_counter": 42,
                "content_ledger": {
                    "recent_drafts": [{"queue_number": 1}],
                    "category_counts_this_week": {
                        "authority": 5,
                        "translation": 4,
                        "personal": 3,
                        "growth": 2,
                    },
                    "saveable_this_week": 7,
                    "week_start": "1999-01-01",
                },
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            state, recovered, rolled_over = load_state(state_path)
            self.assertFalse(recovered)
            self.assertTrue(rolled_over)
            self.assertEqual(state["content_ledger"]["saveable_this_week"], 0)
            self.assertEqual(
                state["content_ledger"]["category_counts_this_week"],
                {"authority": 0, "translation": 0, "personal": 0, "growth": 0},
            )

    def test_save_state_is_atomic_and_roundtrips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state = {
                "last_commit_sha": "def456",
                "queue_counter": 3,
                "processed_commits": ["a", "b", "c"],
                "content_ledger": {
                    "recent_drafts": [],
                    "category_counts_this_week": {
                        "authority": 1,
                        "translation": 1,
                        "personal": 1,
                        "growth": 0,
                    },
                    "saveable_this_week": 1,
                    "week_start": "2026-02-09",
                },
            }
            save_state(state_path, state)
            loaded, recovered, _ = load_state(state_path)
            self.assertFalse(recovered)
            self.assertEqual(loaded["last_commit_sha"], "def456")
            self.assertEqual(loaded["queue_counter"], 3)


if __name__ == "__main__":
    unittest.main()

