from __future__ import annotations

import json
import unittest
from pathlib import Path

from memova_collector.extraction import extract_thread

FIXTURES = Path(__file__).parent / "fixtures"


class ExtractionTests(unittest.TestCase):
    def test_collects_all_visible_messages_and_excludes_sensitive_items(self) -> None:
        payload = json.loads((FIXTURES / "app-server-history-v1.json").read_text())
        thread, diagnostics = extract_thread(
            payload["threads"]["thread-active-001"],
            archived=False,
        )

        self.assertEqual(len(thread["messages"]), 5)
        self.assertEqual(
            [message["phase"] for message in thread["messages"]],
            [None, "commentary", None, "commentary", "final_answer"],
        )
        encoded = json.dumps(thread, ensure_ascii=False)
        self.assertNotIn("TOKEN=secret", encoded)
        self.assertNotIn("reasoning-secret", encoded)
        self.assertNotIn("/secret.txt", encoded)
        self.assertNotIn("/private/example.png", encoded)
        self.assertEqual(diagnostics["excluded_reasoning"], 1)
        self.assertEqual(diagnostics["excluded_commandExecution"], 1)
        self.assertEqual(diagnostics["excluded_fileChange"], 1)
        self.assertEqual(diagnostics["excluded_non_text_part"], 1)


if __name__ == "__main__":
    unittest.main()
