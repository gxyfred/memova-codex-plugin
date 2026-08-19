from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).parents[1] / "hooks" / "write_sync_hint.py"


class HookTests(unittest.TestCase):
    def _run(self, plugin_data: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PLUGIN_DATA"] = str(plugin_data)
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )

    def test_hint_contains_identifiers_but_no_conversation_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_data = Path(temp_dir)
            secret = "do-not-copy-this-prompt-or-response"
            result = self._run(
                plugin_data,
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "session-123",
                    "turn_id": "turn-456",
                    "prompt": secret,
                    "last_assistant_message": secret,
                    "transcript_path": f"/tmp/{secret}.jsonl",
                    "cwd": f"/tmp/{secret}",
                },
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {"continue": True})
            spool = plugin_data / "conversation-sync" / "hints.jsonl"
            raw = spool.read_text(encoding="utf-8")
            self.assertNotIn(secret, raw)
            hint = json.loads(raw)
            self.assertEqual(
                set(hint),
                {"schema_version", "event", "session_id", "turn_id", "observed_at"},
            )
            self.assertEqual(hint["session_id"], "session-123")
            self.assertEqual(hint["event"], "UserPromptSubmit")

    def test_invalid_input_fails_open_without_creating_spool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_data = Path(temp_dir)
            environment = dict(os.environ)
            environment["PLUGIN_DATA"] = str(plugin_data)
            result = subprocess.run(
                [sys.executable, str(HOOK)],
                input="not-json",
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {"continue": True})
            self.assertFalse((plugin_data / "conversation-sync").exists())


if __name__ == "__main__":
    unittest.main()
