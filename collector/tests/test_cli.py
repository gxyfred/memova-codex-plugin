from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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
                        "--accept-privacy-notice-version",
                        "memova_collector_privacy_2026-08-19",
                        "--accept-user-agreement-version",
                        "memova_collector_terms_2026-08-19",
                    ]
                )
            self.assertEqual(result, 0)
            configured_payload = json.loads(configured.getvalue())
            self.assertEqual(configured_payload["status"], "configured_for_v5")
            self.assertEqual(configured_payload["knowledge_mode"], "knowledge_v5")
            self.assertTrue(configured_payload["project_context_enabled"])
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                self.assertEqual(ledger.get_metadata("project_context_enabled"), "true")
                self.assertEqual(ledger.get_metadata("project_context_mode"), "minimal")
                self.assertEqual(ledger.get_metadata("knowledge_mode"), "knowledge_v5")

            full_state = Path(temp_dir) / "full-state"
            full = io.StringIO()
            with redirect_stdout(full):
                result = main(
                    [
                        "setup",
                        "--state-dir",
                        str(full_state),
                        "--accept-policy",
                        "--accept-privacy-notice-version",
                        "memova_collector_privacy_2026-08-19",
                        "--accept-user-agreement-version",
                        "memova_collector_terms_2026-08-19",
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

    def test_diagnose_is_content_free_and_reports_v5_recovery_state(self) -> None:
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
                ledger.set_metadata("preview_source", "live")
                ledger.set_metadata("preview_completed_at", "2026-08-15T00:00:00Z")
                ledger.set_metadata("knowledge_v5_retry_required", "true")
            (state_dir / "knowledge-v5").mkdir()
            (state_dir / "knowledge-v5" / "current-run.json").write_text(
                '{"state_schema":1}',
                encoding="utf-8",
            )
            output = io.StringIO()
            with (
                patch(
                    "memova_collector.cli.inspect_capabilities",
                    return_value={"supported": True, "reasons": []},
                ),
                patch(
                    "memova_collector.cli.CollectorOAuthClient.status",
                    return_value={"connected": True},
                ),
                redirect_stdout(output),
            ):
                result = main(["diagnose", "--state-dir", str(state_dir)])

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 2)
            self.assertEqual(payload["knowledge_mode"], "knowledge_v5")
            self.assertFalse(payload["content_read"])
            self.assertFalse(payload["network_request_performed"])
            self.assertTrue(payload["checks"]["knowledge_v5_run_pending"])
            self.assertIn("resume", " ".join(payload["recommendations"]).lower())

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

    def test_preview_reads_only_selected_threads(self) -> None:
        fixture = (
            Path(__file__).parent / "fixtures" / "app-server-history-v1.json"
        )
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(
                [
                    "preview",
                    "--fixture",
                    str(fixture),
                    "--thread-id",
                    "thread-active-001",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["listed_thread_count"], 1)
        self.assertEqual(payload["read_thread_count"], 1)
        self.assertEqual(payload["bounded_thread_ids"], ["thread-active-001"])
        self.assertFalse(payload["persisted_after_preview"])
        self.assertFalse(payload["remote_upload_performed"])


if __name__ == "__main__":
    unittest.main()
