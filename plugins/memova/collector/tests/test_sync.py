from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memova_collector.fixtures import FixtureThreadSource
from memova_collector.contracts import build_ack
from memova_collector.ledger import Ledger
from memova_collector.sinks import FailingSink, MockSink
from memova_collector.sync import SyncEngine

FIXTURES = Path(__file__).parent / "fixtures"


class SyncTests(unittest.TestCase):
    def _engine(self, source, ledger, sink):
        return SyncEngine(
            source=source,
            ledger=ledger,
            sink=sink,
            consent_id="consent-test-001",
            device_id="device-test-001",
        )

    def test_bounded_sync_reads_and_checkpoints_only_selected_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = FixtureThreadSource(FIXTURES / "app-server-history-v1.json")
            sink = MockSink()
            with Ledger(Path(temp_dir) / "ledger.sqlite3") as ledger:
                result = SyncEngine(
                    source=source,
                    ledger=ledger,
                    sink=sink,
                    consent_id="consent-test-001",
                    device_id="device-test-001",
                    thread_ids={"thread-active-001"},
                ).run_once()

                self.assertEqual(result["listed_thread_count"], 1)
                self.assertEqual(result["read_thread_count"], 1)
                self.assertEqual(result["bounded_thread_ids"], ["thread-active-001"])
                self.assertEqual(source.read_ids, ["thread-active-001"])
                self.assertEqual(ledger.status()["thread_checkpoint_count"], 1)
                sent_ids = {
                    thread["external_thread_id"]
                    for batch in sink.received
                    for thread in batch["threads"]
                }
                self.assertEqual(sent_ids, {"thread-active-001"})

    def test_bounded_sync_refuses_unrelated_pending_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with Ledger(Path(temp_dir) / "ledger.sqlite3") as ledger:
                with self.assertRaises(RuntimeError):
                    self._engine(
                        FixtureThreadSource(FIXTURES / "app-server-history-v1.json"),
                        ledger,
                        FailingSink(),
                    ).run_once()
                with self.assertRaisesRegex(RuntimeError, "unselected threads"):
                    SyncEngine(
                        source=FixtureThreadSource(FIXTURES / "app-server-history-v1.json"),
                        ledger=ledger,
                        sink=MockSink(),
                        consent_id="consent-test-001",
                        device_id="device-test-001",
                        thread_ids={"thread-active-1"},
                    ).run_once()

    def test_initial_sync_then_noop_is_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with Ledger(Path(temp_dir) / "ledger.sqlite3") as ledger:
                first_source = FixtureThreadSource(FIXTURES / "app-server-history-v1.json")
                first_sink = MockSink()
                first = self._engine(first_source, ledger, first_sink).run_once()
                second_source = FixtureThreadSource(FIXTURES / "app-server-history-v1.json")
                second_sink = MockSink()
                second = self._engine(second_source, ledger, second_sink).run_once()

                self.assertEqual(first["listed_thread_count"], 2)
                self.assertEqual(first["read_thread_count"], 2)
                self.assertEqual(first["changed_message_count"], 7)
                self.assertEqual(second["read_thread_count"], 0)
                self.assertEqual(second["staged_batch_count"], 0)
                self.assertEqual(second_sink.received, [])
                self.assertEqual(ledger.status()["acknowledged_item_count"], 7)

    def test_existing_disabled_context_is_preserved_and_modes_are_explicit(self) -> None:
        class ContextSource:
            def list_threads(self, *, archived: bool):
                if archived:
                    return []
                return [
                    {
                        "id": "context-thread",
                        "updatedAt": 1,
                        "source": {"kind": "cli"},
                        "cwd": "/private/example/repo",
                        "gitInfo": {
                            "originUrl": "https://example.test/private/repo.git",
                        },
                    }
                ]

            def read_thread(self, thread_id: str):
                return {
                    "id": thread_id,
                    "updatedAt": 1,
                    "source": {"kind": "cli"},
                    "cwd": "/private/example/repo",
                    "gitInfo": {
                        "originUrl": "https://example.test/private/repo.git",
                    },
                    "turns": [
                        {
                            "id": "turn-1",
                            "items": [
                                {
                                    "type": "userMessage",
                                    "id": "item-1",
                                    "content": [{"type": "text", "text": "A decision"}],
                                }
                            ],
                        }
                    ],
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            with Ledger(Path(temp_dir) / "disabled.sqlite3") as ledger:
                disabled_sink = MockSink()
                self._engine(ContextSource(), ledger, disabled_sink).run_once()
                self.assertNotIn("project_context", disabled_sink.received[0]["threads"][0])
            with Ledger(Path(temp_dir) / "enabled.sqlite3") as ledger:
                ledger.set_metadata("project_context_enabled", "true")
                enabled_sink = MockSink()
                self._engine(ContextSource(), ledger, enabled_sink).run_once()
                context = enabled_sink.received[0]["threads"][0]["project_context"]
                self.assertIn("repository_display_name", context)
            with Ledger(Path(temp_dir) / "minimal.sqlite3") as ledger:
                ledger.set_metadata("project_context_enabled", "true")
                ledger.set_metadata("project_context_mode", "minimal")
                minimal_sink = MockSink()
                self._engine(ContextSource(), ledger, minimal_sink).run_once()
                context = minimal_sink.received[0]["threads"][0]["project_context"]
                self.assertNotIn("repository_display_name", context)

    def test_changed_thread_sends_only_new_edited_and_deleted_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with Ledger(Path(temp_dir) / "ledger.sqlite3") as ledger:
                self._engine(
                    FixtureThreadSource(FIXTURES / "app-server-history-v1.json"),
                    ledger,
                    MockSink(),
                ).run_once()
                sink = MockSink()
                result = self._engine(
                    FixtureThreadSource(FIXTURES / "app-server-history-v2.json"),
                    ledger,
                    sink,
                ).run_once()

                messages = [
                    message
                    for batch in sink.received
                    for thread in batch["threads"]
                    for message in thread["messages"]
                ]
                operations = {
                    message["external_item_id"]: message["operation"] for message in messages
                }
                self.assertEqual(result["read_thread_count"], 1)
                self.assertEqual(result["changed_message_count"], 3)
                self.assertEqual(operations["assistant-commentary-1"], "delete")
                self.assertEqual(operations["assistant-commentary-3"], "upsert")
                self.assertEqual(operations["assistant-final-2"], "upsert")
                self.assertEqual(ledger.status()["acknowledged_item_count"], 7)

    def test_checkpoint_advances_only_after_ack_and_outbox_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with Ledger(Path(temp_dir) / "ledger.sqlite3") as ledger:
                with self.assertRaises(RuntimeError):
                    self._engine(
                        FixtureThreadSource(FIXTURES / "app-server-history-v1.json"),
                        ledger,
                        FailingSink(),
                    ).run_once()
                failed_status = ledger.status()
                self.assertEqual(failed_status["pending_batch_count"], 1)
                self.assertEqual(failed_status["thread_checkpoint_count"], 0)
                self.assertEqual(failed_status["acknowledged_item_count"], 0)

                sink = MockSink()
                recovered = self._engine(
                    FixtureThreadSource(FIXTURES / "app-server-history-v1.json"),
                    ledger,
                    sink,
                ).run_once()
                self.assertEqual(recovered["acknowledged_batch_count"], 1)
                self.assertEqual(recovered["read_thread_count"], 0)
                self.assertEqual(ledger.status()["pending_batch_count"], 0)
                self.assertEqual(ledger.status()["thread_checkpoint_count"], 2)

    def test_chunked_thread_checkpoint_waits_for_every_batch_ack(self) -> None:
        class LargeSource:
            def __init__(self) -> None:
                self.read_count = 0

            def list_threads(self, *, archived: bool):
                if archived:
                    return []
                return [{"id": "large-thread", "updatedAt": 1, "source": {"kind": "cli"}}]

            def read_thread(self, thread_id: str):
                self.read_count += 1
                return {
                    "id": thread_id,
                    "updatedAt": 1,
                    "source": {"kind": "cli"},
                    "turns": [
                        {
                            "id": "large-turn",
                            "items": [
                                {
                                    "type": "userMessage",
                                    "id": f"large-item-{index}",
                                    "content": [{"type": "text", "text": f"message {index}"}],
                                }
                                for index in range(205)
                            ],
                        },
                    ],
                }

        class FailAfterOneSink:
            target = "mock"

            def __init__(self) -> None:
                self.count = 0

            def send(self, batch):
                self.count += 1
                if self.count == 2:
                    raise RuntimeError("synthetic second-batch failure")
                return build_ack(batch)

        with tempfile.TemporaryDirectory() as temp_dir:
            source = LargeSource()
            with Ledger(Path(temp_dir) / "ledger.sqlite3") as ledger:
                with self.assertRaises(RuntimeError):
                    self._engine(source, ledger, FailAfterOneSink()).run_once()
                self.assertEqual(ledger.status()["acknowledged_item_count"], 200)
                self.assertEqual(ledger.status()["pending_batch_count"], 1)
                self.assertEqual(ledger.status()["thread_checkpoint_count"], 0)

                recovered = self._engine(source, ledger, MockSink()).run_once()
                self.assertEqual(recovered["read_thread_count"], 0)
                self.assertEqual(ledger.status()["acknowledged_item_count"], 205)
                self.assertEqual(ledger.status()["thread_checkpoint_count"], 1)

    def test_switching_delivery_target_replays_without_losing_history(self) -> None:
        class SecondTargetSink(MockSink):
            target = "rest"

        with tempfile.TemporaryDirectory() as temp_dir:
            with Ledger(Path(temp_dir) / "ledger.sqlite3") as ledger:
                first = self._engine(
                    FixtureThreadSource(FIXTURES / "app-server-history-v1.json"),
                    ledger,
                    MockSink(),
                ).run_once()
                second_sink = SecondTargetSink()
                second = self._engine(
                    FixtureThreadSource(FIXTURES / "app-server-history-v1.json"),
                    ledger,
                    second_sink,
                ).run_once()

                self.assertEqual(first["changed_message_count"], 7)
                self.assertEqual(second["changed_message_count"], 7)
                self.assertEqual(second["read_thread_count"], 2)
                self.assertEqual(len(second_sink.received), 1)
                self.assertEqual(ledger.status()["thread_checkpoint_count"], 4)


if __name__ == "__main__":
    unittest.main()
