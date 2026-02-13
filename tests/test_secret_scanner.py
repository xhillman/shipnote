from __future__ import annotations

import unittest

from shipnote.secret_scanner import REDACTION_TOKEN, redact_diff


class SecretScannerTests(unittest.TestCase):
    def test_redacts_multiple_patterns(self) -> None:
        raw = "token sk-abcdefghijklmnopqrstuvwxyz1234 and password=hello"
        patterns = [
            r"(sk-[a-zA-Z0-9]{20,})",
            r"password\s*[:=]\s*[\"']?([^\"'\s]+)",
        ]
        redacted, count = redact_diff(raw, patterns)
        self.assertEqual(count, 2)
        self.assertEqual(redacted.count(REDACTION_TOKEN), 2)
        self.assertNotIn("hello", redacted)


if __name__ == "__main__":
    unittest.main()

