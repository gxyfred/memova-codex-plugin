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
    _sanitize_invalid_link_json,
)
from memova_collector.ledger import Ledger
from memova_collector.oauth import OAuthHttpError

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


def _manual_change(*, content: str = "# Personal Manual\n\nDurable body.\n") -> dict:
    change_id = str(uuid.uuid4())
    return {
        "change_id": change_id,
        "object_id": MANUAL_ID,
        "object_type": "personal_manual",
        "operation": "create",
        "expected_revision": None,
        "canonical_format": "markdown",
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
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
    def test_invalid_model_link_json_is_downgraded_to_plain_label(self) -> None:
        changeset = {
            "object_changes": [
                {
                    "content": (
                        "[Project](memova://object/30000000-0000-4000-8000-000000000012)"
                        '<!--memova-link:v1 {"link_id":"broken",}-->'
                    )
                }
            ]
        }

        _sanitize_invalid_link_json(changeset)

        self.assertEqual(changeset["object_changes"][0]["content"], "Project")

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

    def test_resumed_changeset_rebuilds_frontmatter_before_submit(self) -> None:
        idempotency_key = "knowledge-v5-changeset:resumed-frontmatter"
        change_id = "20000000-0000-4000-8000-000000000004"
        changeset = _changeset(lease_id=LEASE_ID, idempotency_key=idempotency_key)
        changeset["object_changes"] = [
            {
                "change_id": change_id,
                "object_id": MANUAL_ID,
                "object_type": "personal_manual",
                "operation": "create",
                "expected_revision": None,
                "canonical_format": "markdown",
                "content": "---\nbad: model header\n---\n# Personal Manual\n",
                "content_sha256": "0" * 64,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            KnowledgeV5StateStore(state_dir).save(
                {
                    "state_schema": 1,
                    "plan_request": {},
                    "plan": _plan(),
                    "lease": _lease(),
                    "changeset_idempotency_key": idempotency_key,
                    "changeset": changeset,
                }
            )
            client = _FakeClient(_plan())
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                result = KnowledgeV5AnalyzerLoop(
                    client=client,
                    runner=_FakeRunner(),
                    ledger=ledger,
                    state_dir=state_dir,
                    device_id="device-1",
                ).run_once(trigger=False)

        self.assertEqual(result["results"]["accepted"], 0)
        submitted = client.submitted[0]["object_changes"][0]
        self.assertEqual(
            submitted["content"],
            "---\n"
            "memova_schema: knowledge-object/v1\n"
            f"object_id: {MANUAL_ID}\n"
            "object_type: personal_manual\n"
            f"revision: {change_id}\n"
            "---\n"
            "# Personal Manual\n",
        )
        self.assertEqual(
            submitted["content_sha256"],
            hashlib.sha256(submitted["content"].encode("utf-8")).hexdigest(),
        )

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
            workspace = Path(command[command.index("--cd") + 1])
            captured["thread_index"] = json.loads(
                (workspace / "analyzer-thread-index.json").read_text(encoding="utf-8")
            )
            output_path = Path(command[command.index("--output-last-message") + 1])
            idempotency_key = "knowledge-v5-changeset:test-runner"
            changeset = _changeset(lease_id=LEASE_ID, idempotency_key=idempotency_key)
            changeset["object_changes"] = [_manual_change()]
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
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
            self.assertIn("--json", captured["command"])
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
            self.assertEqual(result["client_usage"]["source"], "unavailable")
            self.assertIn("analyzer-thread-index.json", captured["prompt"])
            self.assertEqual(captured["thread_index"], [])
            self.assertFalse((runner.workspace_root / RUN_ID).exists())

    def test_runner_attaches_codex_jsonl_token_usage(self) -> None:
        content = _bundle()
        plan = _plan(bundle=content)

        def fake_process(command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            changeset = _changeset(
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:usage",
            )
            changeset["object_changes"] = [_manual_change()]
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
            event = {
                "type": "turn.completed",
                "model": "gpt-test",
                "usage": {
                    "input_tokens": 120,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                },
            }
            return type(
                "Completed",
                (),
                {"returncode": 0, "stdout": json.dumps(event) + "\n"},
            )()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                process_runner=fake_process,
            ).analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:usage",
            )

        self.assertEqual(
            result["client_usage"],
            {
                "source": "codex_cli_jsonl",
                "model": "gpt-test",
                "input_tokens": 120,
                "cached_input_tokens": 20,
                "output_tokens": 30,
                "analyzer_duration_ms": result["client_usage"]["analyzer_duration_ms"],
            },
        )

    def test_runner_adaptively_splits_incomplete_batches_and_aggregates_usage(self) -> None:
        thread_ids = [
            "30000000-0000-4000-8000-000000000001",
            "30000000-0000-4000-8000-000000000002",
        ]
        manifest = {
            "inputs": [
                {
                    "input_type": "changed_thread",
                    "thread_id": thread_id,
                    "relative_path": f"inputs/changed-threads/{thread_id}.json",
                }
                for thread_id in thread_ids
            ]
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("SKILL.md", "# Analyzer\n")
            archive.writestr("bundle.json", json.dumps(manifest))
            archive.writestr("wiki-index.md", "# Wiki\n")
            archive.writestr(
                "contracts/changeset-v1.schema.json",
                json.dumps({"type": "object"}),
            )
            for thread_id in thread_ids:
                archive.writestr(
                    f"inputs/changed-threads/{thread_id}.json",
                    json.dumps({"thread_id": thread_id, "messages": []}),
                )
        content = output.getvalue()
        plan = _plan(bundle=content)
        plan["work_items"] = [
            {
                "work_type": "changed_thread",
                "object_id": thread_id,
                "operation": "create",
                "expected_revision": None,
                "source_hash": "a" * 64,
            }
            for thread_id in thread_ids
        ] + plan["work_items"]
        calls: list[list[dict]] = []
        thread_indexes: list[list[dict]] = []

        def fake_process(command, **kwargs):
            work_items = json.loads(kwargs["input"].split("Authorized work_items=", 1)[1])
            calls.append(work_items)
            workspace = Path(command[command.index("--cd") + 1])
            thread_indexes.append(
                json.loads(
                    (workspace / "analyzer-thread-index.json").read_text(
                        encoding="utf-8"
                    )
                )
            )
            changeset = _changeset(
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:batches",
            )
            changeset["object_changes"] = []
            emitted_work_items = work_items[:-1] if len(work_items) > 1 else work_items
            for item in emitted_work_items:
                object_type = (
                    "codex_session"
                    if item["work_type"] == "changed_thread"
                    else "personal_manual"
                )
                body = f"# {object_type}\n\nGenerated.\n"
                change = _manual_change(content=body)
                change.update(
                    {
                        "object_id": item["object_id"],
                        "object_type": object_type,
                        "operation": item["operation"],
                        "expected_revision": item["expected_revision"],
                    }
                )
                changeset["object_changes"].append(change)
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
            event = {
                "type": "turn.completed",
                "model": "gpt-test",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 3,
                },
            }
            return type(
                "Completed",
                (),
                {"returncode": 0, "stdout": json.dumps(event) + "\n"},
            )()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                process_runner=fake_process,
                max_work_items_per_call=2,
                max_parallel_analyzer_batches=1,
            ).analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:batches",
            )

        self.assertEqual([len(batch) for batch in calls], [2, 1, 1, 1])
        self.assertTrue(all(len(index) == 2 for index in thread_indexes))
        self.assertEqual(
            {item["thread_id"] for item in thread_indexes[0]},
            set(thread_ids),
        )
        self.assertEqual(len(result["object_changes"]), 3)
        self.assertEqual(result["client_usage"]["input_tokens"], 40)
        self.assertEqual(result["client_usage"]["cached_input_tokens"], 8)
        self.assertEqual(result["client_usage"]["output_tokens"], 12)

    def test_runner_rejects_empty_result_for_authorized_work(self) -> None:
        content = _bundle()
        plan = _plan(bundle=content)

        def fake_process(command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(
                json.dumps(
                    _changeset(
                        lease_id=LEASE_ID,
                        idempotency_key="knowledge-v5-changeset:empty",
                    )
                ),
                encoding="utf-8",
            )
            return type("Completed", (), {"returncode": 0})()

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(RuntimeError, "exactly one change"):
                CodexKnowledgeV5Runner(
                    state_dir=Path(temp_dir),
                    process_runner=fake_process,
                ).analyze(
                    bundle=content,
                    plan=plan,
                    lease_id=LEASE_ID,
                    idempotency_key="knowledge-v5-changeset:empty",
                )

    def test_runner_uses_dedicated_business_association_pass(self) -> None:
        thread_id = "30000000-0000-4000-8000-000000000011"
        business_id = "30000000-0000-4000-8000-000000000012"
        manifest = {
            "inputs": [
                {
                    "input_type": "changed_thread",
                    "thread_id": thread_id,
                    "relative_path": f"inputs/changed-threads/{thread_id}.json",
                }
            ],
            "objects": [
                {
                    "object_id": business_id,
                    "object_type": "note",
                    "bundle_role": "business_source",
                    "relative_path": f"objects/{business_id}/document.md",
                }
            ],
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("SKILL.md", "# Analyzer\n")
            archive.writestr("bundle.json", json.dumps(manifest))
            archive.writestr("wiki-index.md", "# Wiki\n")
            archive.writestr(
                "contracts/changeset-v1.schema.json",
                json.dumps({"type": "object"}),
            )
            archive.writestr(
                f"inputs/changed-threads/{thread_id}.json",
                json.dumps({"thread_id": thread_id, "title": "Business review"}),
            )
            archive.writestr(
                f"objects/{business_id}/document.md",
                "# Business review note\n",
            )
        content = output.getvalue()
        plan = _plan(bundle=content)
        plan["work_items"] = [
            {
                "work_type": "changed_thread",
                "object_id": thread_id,
                "operation": "create",
                "expected_revision": None,
                "source_hash": "b" * 64,
            }
        ]
        prompts: list[str] = []

        def fake_process(command, **kwargs):
            prompts.append(kwargs["input"])
            changeset = _changeset(
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:association",
            )
            body = "# Business review\n\nDigest.\n"
            if "dedicated cross-network association pass" in kwargs["input"]:
                metadata = {
                    "link_id": "30000000-0000-4000-8000-000000000013",
                    "target_object_id": business_id,
                    "relation": "related_to",
                    "origin": "codex",
                    "origin_ref": f"analyzer:{RUN_ID}",
                    "target_anchor": None,
                }
                body += (
                    f"[Business note](memova://object/{business_id})"
                    f"<!--memova-link:v1 {json.dumps(metadata, separators=(',', ':'))}-->\n"
                )
            change = _manual_change(content=body)
            change.update(
                {
                    "object_id": thread_id,
                    "object_type": "codex_session",
                    "operation": "create",
                    "expected_revision": None,
                }
            )
            changeset["object_changes"] = [change]
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
            event = {
                "type": "turn.completed",
                "model": "gpt-test",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 3,
                },
            }
            return type(
                "Completed",
                (),
                {"returncode": 0, "stdout": json.dumps(event) + "\n"},
            )()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                process_runner=fake_process,
            ).analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:association",
            )

        self.assertEqual(len(prompts), 2)
        self.assertIn("dedicated cross-network association pass", prompts[1])
        self.assertIn("<!--memova-link:v1", result["object_changes"][0]["content"])
        self.assertEqual(result["client_usage"]["input_tokens"], 20)

    def test_runner_preserves_digest_when_association_pass_drops_link(self) -> None:
        thread_id = "30000000-0000-4000-8000-000000000021"
        business_id = "30000000-0000-4000-8000-000000000022"
        manifest = {
            "inputs": [
                {
                    "input_type": "changed_thread",
                    "thread_id": thread_id,
                    "relative_path": f"inputs/changed-threads/{thread_id}.json",
                }
            ],
            "objects": [
                {
                    "object_id": business_id,
                    "object_type": "note",
                    "bundle_role": "business_source",
                    "relative_path": f"objects/{business_id}/document.md",
                }
            ],
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("SKILL.md", "# Analyzer\n")
            archive.writestr("bundle.json", json.dumps(manifest))
            archive.writestr("wiki-index.md", "# Wiki\n")
            archive.writestr(
                "contracts/changeset-v1.schema.json",
                json.dumps({"type": "object"}),
            )
            archive.writestr(
                f"inputs/changed-threads/{thread_id}.json",
                json.dumps({"thread_id": thread_id, "title": "Preserve links"}),
            )
            archive.writestr(f"objects/{business_id}/document.md", "# Source note\n")
        content = output.getvalue()
        plan = _plan(bundle=content)
        plan["work_items"] = [
            {
                "work_type": "changed_thread",
                "object_id": thread_id,
                "operation": "create",
                "expected_revision": None,
                "source_hash": "c" * 64,
            }
        ]

        metadata = {
            "link_id": "30000000-0000-4000-8000-000000000023",
            "target_object_id": business_id,
            "relation": "related_to",
            "origin": "codex",
            "origin_ref": f"analyzer:{RUN_ID}",
            "target_anchor": None,
        }
        preserved_link = (
            f"[Source note](memova://object/{business_id})"
            f"<!--memova-link:v1 {json.dumps(metadata, separators=(',', ':'))}-->"
        )

        def fake_process(command, **kwargs):
            changeset = _changeset(
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:association-preserve",
            )
            body = "# Preserve links\n\nDigest.\n"
            if "dedicated cross-network association pass" not in kwargs["input"]:
                body += preserved_link + "\n"
            change = _manual_change(content=body)
            change.update(
                {
                    "object_id": thread_id,
                    "object_type": "codex_session",
                    "operation": "create",
                    "expected_revision": None,
                }
            )
            changeset["object_changes"] = [change]
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
            event = {
                "type": "turn.completed",
                "model": "gpt-test",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 3,
                },
            }
            return type(
                "Completed",
                (),
                {"returncode": 0, "stdout": json.dumps(event) + "\n"},
            )()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                process_runner=fake_process,
            ).analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:association-preserve",
            )

        self.assertIn(preserved_link, result["object_changes"][0]["content"])
        self.assertEqual(result["client_usage"]["input_tokens"], 20)

    def test_runner_recomputes_model_supplied_content_hash(self) -> None:
        content = _bundle()
        plan = _plan(bundle=content)
        document = "# Deterministic content\n"

        def fake_process(command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            changeset = _changeset(
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:hash-normalization",
            )
            changeset["object_changes"] = [
                {
                    **_manual_change(content=document),
                    "content": document,
                    "content_sha256": "0" * 64,
                }
            ]
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
            return type("Completed", (), {"returncode": 0})()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                process_runner=fake_process,
            ).analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:hash-normalization",
            )

        self.assertEqual(
            result["object_changes"][0]["content_sha256"],
            hashlib.sha256(
                result["object_changes"][0]["content"].encode("utf-8")
            ).hexdigest(),
        )
        self.assertTrue(result["object_changes"][0]["content"].endswith(document))

    def test_runner_replaces_model_frontmatter_with_create_identity(self) -> None:
        content = _bundle()
        plan = _plan(bundle=content)
        change_id = "20000000-0000-4000-8000-000000000001"
        body = "# Personal Manual\n\nDurable body.\n"

        def fake_process(command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            changeset = _changeset(
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:frontmatter-create",
            )
            changeset["object_changes"] = [
                {
                    "change_id": change_id,
                    "object_id": MANUAL_ID,
                    "object_type": "personal_manual",
                    "operation": "create",
                    "expected_revision": None,
                    "canonical_format": "markdown",
                    "content": (
                        "---\n"
                        "memova_schema: knowledge-object/v1\n"
                        f"object_id: {MANUAL_ID}\n"
                        "object_type: personal_manual\n"
                        f"revision: {change_id}\n"
                        "model_extra: rejected-by-server\n"
                        "---\n"
                        f"{body}"
                    ),
                    "content_sha256": "0" * 64,
                }
            ]
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
            return type("Completed", (), {"returncode": 0})()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                process_runner=fake_process,
            ).analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:frontmatter-create",
            )

        document = result["object_changes"][0]["content"]
        self.assertEqual(
            document,
            "---\n"
            "memova_schema: knowledge-object/v1\n"
            f"object_id: {MANUAL_ID}\n"
            "object_type: personal_manual\n"
            f"revision: {change_id}\n"
            "---\n"
            f"{body}",
        )
        self.assertEqual(
            result["object_changes"][0]["content_sha256"],
            hashlib.sha256(document.encode("utf-8")).hexdigest(),
        )

    def test_runner_replaces_frontmatter_with_expected_replace_revision(self) -> None:
        content = _bundle()
        plan = _plan(bundle=content)
        expected_revision = "20000000-0000-4000-8000-000000000002"
        plan["work_items"][0].update(
            {"operation": "replace", "expected_revision": expected_revision}
        )
        body = "# Personal Manual\n\nUpdated body.\n"

        def fake_process(command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            changeset = _changeset(
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:frontmatter-replace",
            )
            changeset["object_changes"] = [
                {
                    "change_id": "20000000-0000-4000-8000-000000000003",
                    "object_id": MANUAL_ID,
                    "object_type": "personal_manual",
                    "operation": "replace",
                    "expected_revision": expected_revision,
                    "canonical_format": "markdown",
                    "content": body,
                    "content_sha256": "0" * 64,
                }
            ]
            output_path.write_text(json.dumps(changeset), encoding="utf-8")
            return type("Completed", (), {"returncode": 0})()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexKnowledgeV5Runner(
                state_dir=Path(temp_dir),
                process_runner=fake_process,
            ).analyze(
                bundle=content,
                plan=plan,
                lease_id=LEASE_ID,
                idempotency_key="knowledge-v5-changeset:frontmatter-replace",
            )

        self.assertEqual(
            result["object_changes"][0]["content"],
            "---\n"
            "memova_schema: knowledge-object/v1\n"
            f"object_id: {MANUAL_ID}\n"
            "object_type: personal_manual\n"
            f"revision: {expected_revision}\n"
            "---\n"
            f"{body}",
        )

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
