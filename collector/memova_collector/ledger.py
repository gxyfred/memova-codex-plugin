from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .contracts import canonical_json, utc_now


def inspect_ledger(path: str | Path) -> dict[str, Any] | None:
    """Read Collector state without creating, migrating, or journaling the database."""

    ledger_path = Path(path).expanduser()
    if not ledger_path.exists():
        return None
    uri = f"file:{ledger_path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            ).fetchall()
        }
        required = {"metadata", "thread_checkpoints", "acknowledged_items", "outbox"}
        if not required.issubset(tables):
            return None
        metadata = {
            str(row["key"]): str(row["value"])
            for row in connection.execute("SELECT key, value FROM metadata").fetchall()
        }
        counts = {
            str(row["status"]): int(row["count"])
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM outbox GROUP BY status",
            ).fetchall()
        }
        return {
            "thread_checkpoint_count": int(
                connection.execute("SELECT COUNT(*) FROM thread_checkpoints").fetchone()[0],
            ),
            "acknowledged_item_count": int(
                connection.execute("SELECT COUNT(*) FROM acknowledged_items").fetchone()[0],
            ),
            "pending_batch_count": int(counts.get("pending", 0)),
            "acked_batch_count": int(counts.get("acked", 0)),
            "paused": metadata.get("paused") == "true",
            "consent_id": metadata.get("consent_id"),
            "device_id": metadata.get("device_id"),
            "metadata": metadata,
        }
    finally:
        connection.close()


class Ledger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        self.connection = sqlite3.connect(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS thread_checkpoints (
                delivery_target TEXT NOT NULL,
                provider TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                acked_updated_at TEXT,
                acked_archived INTEGER NOT NULL DEFAULT 0,
                acked_thread_hash TEXT,
                acknowledged_at TEXT NOT NULL,
                PRIMARY KEY (delivery_target, provider, thread_id)
            );
            CREATE TABLE IF NOT EXISTS acknowledged_items (
                delivery_target TEXT NOT NULL,
                provider TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                acknowledged_at TEXT NOT NULL,
                PRIMARY KEY (delivery_target, provider, thread_id, item_id)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                batch_id TEXT PRIMARY KEY,
                delivery_target TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'acked')),
                created_at TEXT NOT NULL,
                acked_at TEXT,
                ack_json TEXT,
                last_error TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_outbox_status_created
                ON outbox(status, created_at);
            """,
        )
        self.connection.commit()

    def set_metadata(self, key: str, value: str) -> None:
        self.connection.execute(
            """
            INSERT INTO metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.connection.commit()

    def get_metadata(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row is not None else None

    def thread_needs_read(
        self,
        metadata: dict[str, Any],
        *,
        archived: bool,
        delivery_target: str,
    ) -> bool:
        thread_id = str(metadata.get("id") or metadata.get("threadId") or "")
        updated_at = metadata.get("updatedAt") or metadata.get("updated_at")
        row = self.connection.execute(
            """
            SELECT acked_updated_at, acked_archived
            FROM thread_checkpoints
            WHERE delivery_target = ? AND provider = 'codex' AND thread_id = ?
            """,
            (delivery_target, thread_id),
        ).fetchone()
        if row is None:
            return True
        return str(row["acked_updated_at"] or "") != str(updated_at or "") or bool(
            row["acked_archived"],
        ) != archived

    def diff_thread(
        self,
        thread: dict[str, Any],
        *,
        delivery_target: str,
    ) -> dict[str, Any] | None:
        thread_id = str(thread["external_thread_id"])
        rows = self.connection.execute(
            """
            SELECT item_id, content_hash, payload_json
            FROM acknowledged_items
            WHERE delivery_target = ? AND provider = 'codex' AND thread_id = ?
            """,
            (delivery_target, thread_id),
        ).fetchall()
        acknowledged = {str(row["item_id"]): row for row in rows}
        current = {
            str(message["external_item_id"]): message
            for message in thread.get("messages", [])
        }
        changes = [
            message
            for item_id, message in current.items()
            if item_id not in acknowledged
            or str(acknowledged[item_id]["content_hash"]) != str(message["content_hash"])
        ]
        for item_id, row in acknowledged.items():
            if item_id in current:
                continue
            old_payload = json.loads(str(row["payload_json"]))
            changes.append(
                {
                    "operation": "delete",
                    "external_item_id": item_id,
                    "external_turn_id": old_payload.get("external_turn_id") or "unknown",
                    "content_hash": str(row["content_hash"]),
                },
            )
        changes.sort(
            key=lambda item: (
                1 if item.get("operation") == "delete" else 0,
                int(item.get("sequence", 0)),
                str(item.get("external_item_id", "")),
            ),
        )
        checkpoint = self.connection.execute(
            """
            SELECT acked_updated_at, acked_archived, acked_thread_hash
            FROM thread_checkpoints
            WHERE delivery_target = ? AND provider = 'codex' AND thread_id = ?
            """,
            (delivery_target, thread_id),
        ).fetchone()
        metadata_changed = (
            checkpoint is None
            or str(checkpoint["acked_updated_at"] or "") != str(thread.get("updated_at") or "")
            or bool(checkpoint["acked_archived"]) != bool(thread.get("archived"))
            or str(checkpoint["acked_thread_hash"] or "") != str(thread.get("thread_hash") or "")
        )
        if not changes and not metadata_changed:
            return None
        return {**thread, "messages": changes}

    def stage_batch(self, batch: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO outbox(
                batch_id, delivery_target, idempotency_key, payload_json, status, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (
                batch["batch_id"],
                batch["delivery_target"],
                batch["idempotency_key"],
                canonical_json(batch),
                utc_now(),
            ),
        )
        self.connection.commit()

    def pending_batches(self, *, delivery_target: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT payload_json FROM outbox
            WHERE status = 'pending' AND delivery_target = ?
            ORDER BY created_at, batch_id
            """,
            (delivery_target,),
        ).fetchall()
        return [json.loads(str(row["payload_json"])) for row in rows]

    def mark_batch_error(self, batch_id: str, error: str) -> None:
        self.connection.execute(
            "UPDATE outbox SET last_error = ? WHERE batch_id = ?",
            (error[:2000], batch_id),
        )
        self.connection.commit()

    def acknowledge_batch(self, batch: dict[str, Any], ack: dict[str, Any]) -> None:
        if ack.get("status") != "accepted":
            raise ValueError("Only accepted batch acknowledgements may advance the ledger.")
        if ack.get("batch_id") != batch.get("batch_id"):
            raise ValueError("Acknowledgement batch_id does not match the outbox batch.")
        now = str(ack.get("acknowledged_at") or utc_now())
        delivery_target = str(batch["delivery_target"])
        with self.connection:
            self.connection.execute(
                """
                UPDATE outbox
                SET status = 'acked', acked_at = ?, ack_json = ?, last_error = NULL
                WHERE batch_id = ?
                """,
                (now, canonical_json(ack), batch["batch_id"]),
            )
            for thread in batch.get("threads", []):
                thread_id = str(thread["external_thread_id"])
                for message in thread.get("messages", []):
                    item_id = str(message["external_item_id"])
                    if message.get("operation") == "delete":
                        self.connection.execute(
                            """
                            DELETE FROM acknowledged_items
                            WHERE delivery_target = ? AND provider = 'codex'
                              AND thread_id = ? AND item_id = ?
                            """,
                            (delivery_target, thread_id, item_id),
                        )
                        continue
                    self.connection.execute(
                        """
                        INSERT INTO acknowledged_items(
                            delivery_target, provider, thread_id, item_id, turn_id, content_hash,
                            payload_json, acknowledged_at
                        ) VALUES (?, 'codex', ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(delivery_target, provider, thread_id, item_id) DO UPDATE SET
                            turn_id = excluded.turn_id,
                            content_hash = excluded.content_hash,
                            payload_json = excluded.payload_json,
                            acknowledged_at = excluded.acknowledged_at
                        """,
                        (
                            delivery_target,
                            thread_id,
                            item_id,
                            str(message["external_turn_id"]),
                            str(message["content_hash"]),
                            canonical_json(message),
                            now,
                        ),
                    )

            pending_payloads = [
                json.loads(str(row["payload_json"]))
                for row in self.connection.execute(
                    """
                    SELECT payload_json FROM outbox
                    WHERE status = 'pending' AND delivery_target = ?
                    """,
                    (delivery_target,),
                ).fetchall()
            ]
            for thread in batch.get("threads", []):
                thread_id = str(thread["external_thread_id"])
                thread_hash = str(thread.get("thread_hash") or "")
                still_pending = any(
                    any(
                        str(candidate.get("external_thread_id")) == thread_id
                        and str(candidate.get("thread_hash") or "") == thread_hash
                        for candidate in pending.get("threads", [])
                    )
                    for pending in pending_payloads
                )
                if still_pending:
                    continue
                self.connection.execute(
                    """
                    INSERT INTO thread_checkpoints(
                        delivery_target, provider, thread_id, acked_updated_at, acked_archived,
                        acked_thread_hash, acknowledged_at
                    ) VALUES (?, 'codex', ?, ?, ?, ?, ?)
                    ON CONFLICT(delivery_target, provider, thread_id) DO UPDATE SET
                        acked_updated_at = excluded.acked_updated_at,
                        acked_archived = excluded.acked_archived,
                        acked_thread_hash = excluded.acked_thread_hash,
                        acknowledged_at = excluded.acknowledged_at
                    """,
                    (
                        delivery_target,
                        thread_id,
                        str(thread.get("updated_at") or ""),
                        int(bool(thread.get("archived"))),
                        thread_hash,
                        now,
                    ),
                )

    def status(self) -> dict[str, Any]:
        counts = {
            row["status"]: row["count"]
            for row in self.connection.execute(
                "SELECT status, COUNT(*) AS count FROM outbox GROUP BY status",
            ).fetchall()
        }
        return {
            "thread_checkpoint_count": int(
                self.connection.execute("SELECT COUNT(*) FROM thread_checkpoints").fetchone()[0],
            ),
            "acknowledged_item_count": int(
                self.connection.execute("SELECT COUNT(*) FROM acknowledged_items").fetchone()[0],
            ),
            "pending_batch_count": int(counts.get("pending", 0)),
            "acked_batch_count": int(counts.get("acked", 0)),
            "paused": self.get_metadata("paused") == "true",
            "consent_id": self.get_metadata("consent_id"),
            "device_id": self.get_metadata("device_id"),
        }
