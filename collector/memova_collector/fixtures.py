from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FixtureThreadSource:
    def __init__(self, path: str | Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.active = list(payload.get("active", []))
        self.archived = list(payload.get("archived", []))
        self.threads = dict(payload.get("threads", {}))
        self.read_ids: list[str] = []

    def list_threads(self, *, archived: bool) -> list[dict[str, Any]]:
        return list(self.archived if archived else self.active)

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        self.read_ids.append(thread_id)
        payload = self.threads.get(thread_id)
        if not isinstance(payload, dict):
            raise KeyError(f"Fixture thread {thread_id!r} was not found.")
        return json.loads(json.dumps(payload))
