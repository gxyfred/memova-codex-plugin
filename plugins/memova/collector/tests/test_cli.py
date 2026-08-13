from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from memova_collector.cli import main
from memova_collector.contracts import build_consent_record
from memova_collector.ledger import Ledger


class CliTests(unittest.TestCase):
    def test_project_context_defaults_minimal_and_full_mode_is_disclosed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "state"
            disclosure = io.StringIO()
            with redirect_stdout(disclosure):
                result = main(
                    [
                        "setup",
                        "--state-dir",
                        str(state_dir),
                    ]
                )
            disclosed = json.loads(disclosure.getvalue())
            self.assertEqual(result, 2)
            self.assertEqual(disclosed["project_context_mode"], "minimal")
            self.assertEqual(
                disclosed["policy"]["included"]["project_context"],
                "privacy_minimal_repository_identity_v1",
            )

            configured = io.StringIO()
            with redirect_stdout(configured):
                result = main(
                    [
                        "setup",
                        "--state-dir",
                        str(state_dir),
                        "--accept-policy",
                    ]
                )
            self.assertEqual(result, 0)
            self.assertTrue(json.loads(configured.getvalue())["project_context_enabled"])
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                self.assertEqual(ledger.get_metadata("project_context_enabled"), "true")
                self.assertEqual(ledger.get_metadata("project_context_mode"), "minimal")

            full_state = Path(temp_dir) / "full-state"
            full = io.StringIO()
            with redirect_stdout(full):
                result = main(
                    [
                        "setup",
                        "--state-dir",
                        str(full_state),
                        "--accept-policy",
                        "--include-project-context",
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(full.getvalue())["project_context_mode"], "full")

    def test_status_is_read_only_when_state_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "missing-state"
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["status", "--state-dir", str(state_dir)])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "unconfigured")
            self.assertFalse(state_dir.exists())

    def test_paused_scheduled_run_does_not_read_source_or_require_active_consent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "state"
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                ledger.set_metadata("paused", "true")
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "sync-once",
                        "--state-dir",
                        str(state_dir),
                        "--fixture",
                        str(state_dir / "must-not-be-opened.json"),
                    ],
                )
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "paused")

    def test_connect_rejects_fixture_preview_before_oauth_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "state"
            state_dir.mkdir()
            (state_dir / "consent.json").write_text(
                json.dumps(
                    build_consent_record(
                        consent_id="consent-0001",
                        device_id="device-0001",
                    )
                ),
                encoding="utf-8",
            )
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                ledger.set_metadata("preview_source", "fixture")
                ledger.set_metadata("preview_completed_at", "2026-08-11T00:00:00Z")
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["connect", "--state-dir", str(state_dir)])
            self.assertEqual(result, 2)
            self.assertIn("successful live preview", json.loads(output.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
