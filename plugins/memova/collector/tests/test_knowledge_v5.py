from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from memova_collector.knowledge_v5 import (
    CodexKnowledgeV5Runner,
    KnowledgeV5AnalyzerLoop,
    KnowledgeV5StateStore,
)
from memova_collector.oauth import OAuthHttpError
from memova_collector.ledger import Ledger

RUN_ID = "10000000-0000-4000-8000-000000000001"
PLAN_ID = "10000000-0000-4000-8000-000000000002"
BUNDLE_ID = "10000000-0000-4000-8000-000000000003"
LEASE_ID = "10000000-0000-4000-8000-000000000004"
MANUAL_ID = "10000000-0000-4000-8000-000000000005"
NEXT_BUNDLE_ID = "10000000-0000-4000-8000-000000000006"
SERVER_CHECKPOINT = f"v5:{RUN_ID}:{NEXT_BUNDLE_ID}"


def _future() -> str:
    return (datetime.now(UTC) + timedelta(minutes=10)).isoformat()


def _bundle() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("SKILL.md", "# Analyzer\n")
        archive.writestr("bundle.json", "{}\n")
        archive.writestr("wiki-index.md", "# Wiki\n")
        archive.writestr(
            "contracts/changeset-v1.schema.json",
            json.dumps({"type": "object"}),
        )
    return output.getvalue()


def _plan(*, status: str = "planned", bundle: bytes | None = None) -> dict:
    content = bundle or _bundle()
    return {
        "schema_version": "knowledge-sync-plan/v1",
        "analyzer_run_id": RUN_ID,
        "plan_id": PLAN_ID,
        "status": status,
        "bundle_revision": BUNDLE_ID,
        "bundle_sha256": hashlib.sha256(content).hexdigest(),
        "bundle_byte_size": len(content),
        "bundle_download_path": f"/v1/knowledge-v5/bundles/{BUNDLE_ID}",
        "bundle_expires_at": _future(),
        "personal_manual_object_id": MANUAL_ID,
        "work_items": [] if status == "no_work" else [
            {
                "work_type": "personal_manual",
                "object_id": MANUAL_ID,
                "operation": "create",
                "expected_revision": None,
                "source_hash": None,
            }
        ],
        "reused_existing": False,
    }


def _lease() -> dict:
    return {
        "schema_version": "knowledge-analyzer-lease/v1",
        "analyzer_run_id": RUN_ID,
        "plan_id": PLAN_ID,
        "lease_id": LEASE_ID,
        "expires_at": _future(),
        "reused_existing": False,
    }


def _run(*, status: str = "planned", ack: dict | None = None) -> dict:
    return {
        "schema_version": "knowledge-analyzer-run/v1",
        "analyzer_run_id": RUN_ID,
        "plan_id": PLAN_ID,
        "status": status,
        "base_bundle_revision": BUNDLE_ID,
        "lease_expires_at": _future() if status in {"leased", "committing"} else None,
        "server_checkpoint": ack.get("server_checkpoint") if ack else None,
        "completed_at": datetime.now(UTC).isoformat() if status == "completed" else None,
        "ack": ack,
    }


def _changeset(*, lease_id: str, idempotency_key: str) -> dict:
    return {
        "schema_version": "knowledge-changeset/v1",
        "analyzer_run_id": RUN_ID,
        "plan_id": PLAN_ID,
        "lease_id": lease_id,
        "idempotency_key": idempotency_key,
        "base_bundle_revision": BUNDLE_ID,
        "object_changes": [],
    }


def _ack(idempotency_key: str) -> dict:
    return {
        "schema_version": "knowledge-changeset-ack/v1",
        "analyzer_run_id": RUN_ID,
        "idempotency_key": idempotency_key,
        "bundle_revision": NEXT_BUNDLE_ID,
        "server_checkpoint": SERVER_CHECKPOINT,
        "results": [],
    }


class _FakeRunner:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, *, bundle, plan, lease_id, idempotency_key):
        self.calls += 1
        return _changeset(lease_id=lease_id, idempotency_key=idempotency_key)


class _FakeClient:
    def __init__(self, plan: dict, *, fail_submit: bool = False) -> None:
        self.plan = plan
        self.fail_submit = fail_submit
        self.submitted: list[dict] = []
        self.completed_ack: dict | None = None

    def create_sync_plan(self, payload):
        self.plan_request = payload
        return self.plan

    def get_run(self, analyzer_run_id):
        if self.completed_ack is not None:
            return _run(status="completed", ack=self.completed_ack)
        return _run()

    def acquire_lease(self, payload):
        self.lease_request = payload
        return _lease()

    def download_bundle(self, *, plan, lease_id):
        return _bundle()

    def submit_changeset(self, payload):
        self.submitted.append(json.loads(json.dumps(payload)))
        ack = _ack(payload["idempotency_key"])
        if self.fail_submit:
            self.completed_ack = ack
            raise RuntimeError("unknown submit outcome")
        return ack


class KnowledgeV5Tests(unittest.TestCase):
    def test_disabled_backend_defers_v5_without_losing_resumable_state(self) -> None:
        class DisabledClient(_FakeClient):
            def create_sync_plan(self, payload):
                del payload
                raise OAuthHttpError(404, {"error": {"code": "integration.unavailable"}})

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                loop = KnowledgeV5AnalyzerLoop(
                    client=DisabledClient(_plan()),
                    runner=_FakeRunner(),
                    ledger=ledger,
                    state_dir=state_dir,
                    device_id="device-1",
                )
                result = loop.run_once(trigger=True)

                self.assertEqual(result["status"], "unavailable")
                self.assertTrue(result["retry_required"])
                self.assertTrue(result["resume_pending"])
                self.assertIsNone(ledger.get_metadata("knowledge_v5_initialized"))
                self.assertTrue(loop.has_pending_run())

    def test_analyzer_loop_commits_checkpoint_only_after_valid_ack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            client = _FakeClient(_plan())
            runner = _FakeRunner()
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                result = KnowledgeV5AnalyzerLoop(
                    client=client,
                    runner=runner,
                    ledger=ledger,
                    state_dir=state_dir,
                    device_id="device-1",
                ).run_once(trigger=True)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(
                    ledger.get_metadata("knowledge_v5_server_checkpoint"),
                    SERVER_CHECKPOINT,
                )
                self.assertEqual(ledger.get_metadata("knowledge_v5_initialized"), "true")
            self.assertEqual(runner.calls, 1)
            self.assertEqual(len(client.submitted), 1)
            self.assertFalse(KnowledgeV5StateStore(state_dir).path.exists())

    def test_unknown_submit_outcome_recovers_from_server_ack_without_rerunning_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            client = _FakeClient(_plan(), fail_submit=True)
            runner = _FakeRunner()
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                loop = KnowledgeV5AnalyzerLoop(
                    client=client,
                    runner=runner,
                    ledger=ledger,
                    state_dir=state_dir,
                    device_id="device-1",
                )
                with self.assertRaisesRegex(RuntimeError, "unknown submit outcome"):
                    loop.run_once(trigger=True)
                self.assertIsNone(ledger.get_metadata("knowledge_v5_server_checkpoint"))
                self.assertTrue(loop.has_pending_run())

                recovered = loop.run_once(trigger=False)
                self.assertEqual(recovered["status"], "completed")
                self.assertEqual(
                    ledger.get_metadata("knowledge_v5_server_checkpoint"),
                    SERVER_CHECKPOINT,
                )
            self.assertEqual(runner.calls, 1)
            self.assertEqual(len(client.submitted), 1)

    def test_ack_checkpoint_must_bind_the_new_bundle_revision(self) -> None:
        class InvalidCheckpointClient(_FakeClient):
            def submit_changeset(self, payload):
                ack = _ack(payload["idempotency_key"])
                ack["server_checkpoint"] = f"v5:{RUN_ID}:{BUNDLE_ID}"
                return ack

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                with self.assertRaisesRegex(RuntimeError, "new Bundle revision"):
                    KnowledgeV5AnalyzerLoop(
                        client=InvalidCheckpointClient(_plan()),
                        runner=_FakeRunner(),
                        ledger=ledger,
                        state_dir=state_dir,
                        device_id="device-1",
                    ).run_once(trigger=True)
                self.assertIsNone(ledger.get_metadata("knowledge_v5_server_checkpoint"))

    def test_conflict_ack_sets_lightweight_retry_trigger(self) -> None:
        class ConflictClient(_FakeClient):
            def submit_changeset(self, payload):
                ack = _ack(payload["idempotency_key"])
                ack["results"] = [
                    {
                        "change_id": str(uuid.uuid4()),
                        "object_id": MANUAL_ID,
                        "status": "conflict",
                        "revision": None,
                        "error_code": "knowledge_v5.revision_conflict",
                    }
                ]
                return ack

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                result = KnowledgeV5AnalyzerLoop(
                    client=ConflictClient(_plan()),
                    runner=_FakeRunner(),
                    ledger=ledger,
                    state_dir=state_dir,
                    device_id="device-1",
                ).run_once(trigger=True)
                self.assertEqual(result["results"]["conflict"], 1)
                self.assertEqual(ledger.get_metadata("knowledge_v5_retry_required"), "true")

    def test_no_work_initializes_without_invoking_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            runner = _FakeRunner()
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                result = KnowledgeV5AnalyzerLoop(
                    client=_FakeClient(_plan(status="no_work")),
                    runner=runner,
                    ledger=ledger,
                    state_dir=state_dir,
                    device_id="device-1",
                ).run_once(trigger=True)
                self.assertEqual(result["status"], "no_work")
                self.assertEqual(ledger.get_metadata("knowledge_v5_initialized"), "true")
            self.assertEqual(runner.calls, 0)

    def test_no_trigger_and_no_pending_state_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                result = KnowledgeV5AnalyzerLoop(
                    client=_FakeClient(_plan()),
                    runner=_FakeRunner(),
                    ledger=ledger,
                    state_dir=state_dir,
                    device_id="device-1",
                ).run_once(trigger=False)
            self.assertEqual(result, {"status": "skipped", "reason": "no_archived_changes"})
            self.assertFalse(KnowledgeV5StateStore(state_dir).path.exists())

    def test_runner_uses_ephemeral_read_only_exec_and_removes_workspace(self) -> None:
        content = _bundle()
        plan = _plan(bundle=content)
        captured: dict = {}

        def fake_process(command, **kwargs):
            captured["command"] = command
            captured["prompt"] = kwargs["input"]
            output_path = Path(command[command.index("--output-last-message") + 1])
            idempotency_key = "knowledge-v5-changeset:test-runner"
            output_path.write_text(
                json.dumps(_changeset(lease_id=LEASE_ID, idempotency_key=idempotency_key)),
                encoding="utf-8",
            )
            return type("Completed", (), {"returncode": 0})()

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                codex_path="/opt/codex",
                process_runner=fake_process,
            )
            result = runner.analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:test-runner",
            )
            self.assertEqual(result["schema_version"], "knowledge-changeset/v1")
            self.assertIn("--ephemeral", captured["command"])
            self.assertIn("read-only", captured["command"])
            self.assertIn("--ignore-user-config", captured["command"])
            for feature in (
                "plugins",
                "remote_plugin",
                "recommended_plugins",
                "apps",
                "enable_mcp_apps",
            ):
                self.assertIn(feature, captured["command"])
            self.assertFalse((runner.workspace_root / RUN_ID).exists())

    def test_runner_rejects_bundle_hash_mismatch_before_exec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            called = False

            def fake_process(*args, **kwargs):
                nonlocal called
                called = True

            with self.assertRaisesRegex(RuntimeError, "hash"):
                CodexKnowledgeV5Runner(
                    state_dir=Path(temp_dir),
                    process_runner=fake_process,
                ).analyze(
                    bundle=b"x" * len(_bundle()),
                    plan=_plan(),
                    lease_id=LEASE_ID,
                    idempotency_key="knowledge-v5-changeset:test-runner",
                )
            self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
