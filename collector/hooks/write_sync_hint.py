#!/usr/bin/env python3
"""Write a content-free activity hint without parsing the Codex transcript."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "memova_codex_hook_hint_v1"
ALLOWED_EVENTS = frozenset({"UserPromptSubmit", "Stop"})
MAX_INPUT_BYTES = 1_048_576
MAX_SPOOL_BYTES = 1_048_576


def _identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:256] if value else None


def _read_event() -> dict[str, Any] | None:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        return None
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else None


def _rotate_if_needed(path: Path) -> None:
    try:
        if path.stat().st_size >= MAX_SPOOL_BYTES:
            rotated = path.with_suffix(".jsonl.1")
            os.replace(path, rotated)
    except FileNotFoundError:
        return


def _append_hint(plugin_data: Path, payload: dict[str, Any]) -> None:
    spool_dir = plugin_data / "conversation-sync"
    spool_dir.mkdir(parents=True, exist_ok=True)
    try:
        spool_dir.chmod(0o700)
    except OSError:
        pass
    path = spool_dir / "hints.jsonl"
    _rotate_if_needed(path)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)


def main() -> int:
    try:
        event_payload = _read_event()
        if event_payload is not None:
            event = _identifier(event_payload.get("hook_event_name"))
            session_id = _identifier(event_payload.get("session_id"))
            plugin_data = os.environ.get("PLUGIN_DATA")
            if event in ALLOWED_EVENTS and session_id and plugin_data:
                _append_hint(
                    Path(plugin_data),
                    {
                        "schema_version": SCHEMA_VERSION,
                        "event": event,
                        "session_id": session_id,
                        "turn_id": _identifier(event_payload.get("turn_id")),
                        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    },
                )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        # Audit markers are optional. Hook failure must never block or alter the Codex turn.
        pass
    sys.stdout.write('{"continue":true}\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
