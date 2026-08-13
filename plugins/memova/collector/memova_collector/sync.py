from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from .app_server import ThreadSource
from .contracts import build_batch
from .extraction import extract_thread
from .ledger import Ledger
from .sinks import BatchSink

MAX_MESSAGES_PER_BATCH = 200
MAX_THREAD_ENTRIES_PER_BATCH = 20


def _metadata_thread_id(thread: dict[str, Any]) -> str:
    return str(thread.get("id") or thread.get("threadId") or "")


def _split_thread(thread: dict[str, Any]) -> list[dict[str, Any]]:
    messages = list(thread.get("messages", []))
    base = {key: value for key, value in thread.items() if key != "messages"}
    if not messages:
        return [{**base, "messages": []}]
    return [
        {**base, "messages": messages[index : index + MAX_MESSAGES_PER_BATCH]}
        for index in range(0, len(messages), MAX_MESSAGES_PER_BATCH)
    ]


def _chunk_thread_entries(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    message_count = 0
    for entry in entries:
        entry_messages = len(entry.get("messages", []))
        if current and (
            len(current) >= MAX_THREAD_ENTRIES_PER_BATCH
            or message_count + entry_messages > MAX_MESSAGES_PER_BATCH
        ):
            chunks.append(current)
            current = []
            message_count = 0
        current.append(entry)
        message_count += entry_messages
    if current:
        chunks.append(current)
    return chunks


class SyncEngine:
    def __init__(
        self,
        *,
        source: ThreadSource,
        ledger: Ledger,
        sink: BatchSink,
        consent_id: str,
        device_id: str,
    ) -> None:
        self.source = source
        self.ledger = ledger
        self.sink = sink
        self.consent_id = consent_id
        self.device_id = device_id
        self.delivery_target = str(getattr(sink, "target", "mock"))
        fingerprint_secret = self.ledger.get_metadata("repository_fingerprint_secret")
        if fingerprint_secret is None:
            fingerprint_secret = str(uuid.uuid4())
            self.ledger.set_metadata("repository_fingerprint_secret", fingerprint_secret)
        self.project_fingerprint_secret = fingerprint_secret
        self.project_context_enabled = (
            self.ledger.get_metadata("project_context_enabled") == "true"
        )
        fingerprint_key_reader = getattr(sink, "repository_fingerprint_key", None)
        self.workspace_repository_fingerprint_key = (
            fingerprint_key_reader()
            if self.project_context_enabled and callable(fingerprint_key_reader)
            else None
        )

    def _flush_outbox(self) -> int:
        acknowledged = 0
        for batch in self.ledger.pending_batches(delivery_target=self.delivery_target):
            try:
                ack = self.sink.send(batch)
                self.ledger.acknowledge_batch(batch, ack)
                acknowledged += 1
            except Exception as exc:
                self.ledger.mark_batch_error(batch["batch_id"], str(exc))
                raise
        return acknowledged

    def run_once(self) -> dict[str, Any]:
        if self.ledger.get_metadata("paused") == "true":
            return {
                "status": "paused",
                "listed_thread_count": 0,
                "read_thread_count": 0,
                "staged_batch_count": 0,
                "acknowledged_batch_count": 0,
            }

        acknowledged = self._flush_outbox()
        listed: dict[str, tuple[dict[str, Any], bool]] = {}
        for archived in (False, True):
            for metadata in self.source.list_threads(archived=archived):
                thread_id = _metadata_thread_id(metadata)
                if thread_id:
                    listed[thread_id] = (metadata, archived)

        diagnostics: Counter[str] = Counter()
        entries: list[dict[str, Any]] = []
        read_count = 0
        for thread_id, (metadata, archived) in listed.items():
            if not self.ledger.thread_needs_read(
                metadata,
                archived=archived,
                delivery_target=self.delivery_target,
            ):
                continue
            full_thread = self.source.read_thread(thread_id)
            full_thread.setdefault("id", thread_id)
            full_thread.setdefault("updatedAt", metadata.get("updatedAt"))
            full_thread.setdefault("createdAt", metadata.get("createdAt"))
            full_thread.setdefault("title", metadata.get("title") or metadata.get("name"))
            full_thread.setdefault("source", metadata.get("source"))
            full_thread.setdefault("cwd", metadata.get("cwd"))
            full_thread.setdefault("gitInfo", metadata.get("gitInfo"))
            extracted, thread_diagnostics = extract_thread(
                full_thread,
                archived=archived,
                project_fingerprint_secret=(
                    self.project_fingerprint_secret
                    if self.project_context_enabled
                    else None
                ),
                workspace_repository_fingerprint_key=(
                    self.workspace_repository_fingerprint_key
                ),
            )
            read_count += 1
            diagnostics.update(thread_diagnostics)
            delta = self.ledger.diff_thread(
                extracted,
                delivery_target=self.delivery_target,
            )
            if delta is not None:
                entries.extend(_split_thread(delta))

        batches = [
            build_batch(
                consent_id=self.consent_id,
                device_id=self.device_id,
                delivery_target=self.delivery_target,
                threads=chunk,
                diagnostics=dict(diagnostics),
            )
            for chunk in _chunk_thread_entries(entries)
        ]
        for batch in batches:
            self.ledger.stage_batch(batch)
        acknowledged += self._flush_outbox()
        message_count = sum(
            len(thread.get("messages", []))
            for batch in batches
            for thread in batch.get("threads", [])
        )
        return {
            "status": "completed",
            "listed_thread_count": len(listed),
            "read_thread_count": read_count,
            "changed_thread_entry_count": len(entries),
            "changed_message_count": message_count,
            "staged_batch_count": len(batches),
            "acknowledged_batch_count": acknowledged,
            "diagnostics": dict(diagnostics),
        }
