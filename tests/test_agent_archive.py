from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins" / "memova" / "scripts" / "agent_archive.py"


class AgentArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.state = self.root / "state.json"
        self.env = {**os.environ, "MEMOVA_AGENT_ARCHIVE_STATE": str(self.state)}
        self.run_cli("configure", "--vault-root", str(self.vault), "--mode", "ask_each_time")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            ["python3", str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(completed.returncode, expected, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def test_prepare_copies_exact_authorized_output_and_reuses_stable_id(self) -> None:
        output = self.root / "report.md"
        output.write_text("# Result\n\nHello.\n", encoding="utf-8")
        first = self.run_cli(
            "prepare",
            "--source",
            str(output),
            "--task-id",
            "task-1",
            "--source-reference",
            "codex://threads/task-1",
            "--authorize",
        )
        destination = self.vault / "projects" / "Uncategorized" / "report.md"
        self.assertEqual(destination.read_bytes(), output.read_bytes())
        self.assertEqual(first["tool"], "import_agent_file")
        self.assertEqual(
            first["arguments"]["content_sha256"], hashlib.sha256(output.read_bytes()).hexdigest()
        )
        repeated = self.run_cli(
            "prepare",
            "--source",
            str(output),
            "--task-id",
            "task-1",
            "--source-reference",
            "codex://threads/task-1",
            "--authorize",
        )
        self.assertEqual(
            first["arguments"]["idempotency_key"], repeated["arguments"]["idempotency_key"]
        )

        output.write_text("# Result\n\nUpdated.\n", encoding="utf-8")
        second = self.run_cli(
            "prepare",
            "--source",
            str(output),
            "--task-id",
            "task-1",
            "--source-reference",
            "codex://threads/task-1",
            "--authorize",
        )
        self.assertEqual(
            first["arguments"]["stable_node_id"], second["arguments"]["stable_node_id"]
        )
        self.assertEqual(destination.read_bytes(), output.read_bytes())

    def test_scheduled_scan_reads_only_persistently_authorized_manifest(self) -> None:
        self.run_cli(
            "configure", "--vault-root", str(self.vault), "--mode", "always_auto_save"
        )
        output = self.root / "summary.html"
        output.write_text("<h1>Summary</h1>", encoding="utf-8")
        prepared = self.run_cli(
            "prepare",
            "--source",
            str(output),
            "--task-id",
            "task-2",
            "--source-reference",
            "codex://threads/task-2",
        )
        scan = self.run_cli("scan-authorized")
        self.assertEqual(len(scan["requests"]), 1)
        request = scan["requests"][0]
        self.assertEqual(request["arguments"]["archive_mode"], "scheduled")
        self.assertEqual(
            request["arguments"]["stable_node_id"], prepared["arguments"]["stable_node_id"]
        )

    def test_always_auto_save_upgrades_an_existing_exact_manifest_entry(self) -> None:
        output = self.root / "decision.md"
        output.write_text("# Decision\n", encoding="utf-8")
        self.run_cli(
            "prepare",
            "--source",
            str(output),
            "--task-id",
            "task-2b",
            "--source-reference",
            "codex://threads/task-2b",
            "--authorize",
        )
        self.run_cli(
            "configure", "--vault-root", str(self.vault), "--mode", "always_auto_save"
        )
        self.run_cli(
            "prepare",
            "--source",
            str(output),
            "--task-id",
            "task-2b",
            "--source-reference",
            "codex://threads/task-2b",
        )
        scan = self.run_cli("scan-authorized")
        self.assertEqual(len(scan["requests"]), 1)
        self.assertTrue(scan["requests"][0]["arguments"]["authorized_manifest_entry"])

    def test_secret_and_source_code_are_blocked(self) -> None:
        secret = self.root / "secret.md"
        secret.write_text("api_key=super-secret-value", encoding="utf-8")
        blocked = self.run_cli(
            "prepare",
            "--source",
            str(secret),
            "--task-id",
            "task-3",
            "--source-reference",
            "codex://threads/task-3",
            "--authorize",
            expected=2,
        )
        self.assertEqual(blocked["status"], "blocked")

        source = self.root / "module.py"
        source.write_text("print('hello')", encoding="utf-8")
        blocked = self.run_cli(
            "prepare",
            "--source",
            str(source),
            "--task-id",
            "task-3",
            "--source-reference",
            "codex://threads/task-3",
            "--authorize",
            expected=2,
        )
        self.assertEqual(blocked["status"], "blocked")

    def test_no_file_prompt_is_recorded_once(self) -> None:
        self.assertTrue(self.run_cli("ask-status", "--task-id", "task-4")["should_ask"])
        self.run_cli("mark-asked", "--task-id", "task-4")
        self.assertFalse(self.run_cli("ask-status", "--task-id", "task-4")["should_ask"])


if __name__ == "__main__":
    unittest.main()
