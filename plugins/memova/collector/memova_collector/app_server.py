from __future__ import annotations

import json
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Protocol

from .capability import locate_codex
from .contracts import ALLOWED_SOURCE_KINDS, COLLECTOR_VERSION


class ThreadSource(Protocol):
    def list_threads(self, *, archived: bool) -> list[dict[str, Any]]: ...

    def read_thread(self, thread_id: str) -> dict[str, Any]: ...


class AppServerError(RuntimeError):
    pass


class JsonRpcAppServerClient:
    """Minimal read-only JSON-RPC client for a local stdio App Server."""

    def __init__(self, codex_path: str | None = None, *, timeout: float = 30) -> None:
        executable = locate_codex(codex_path)
        if executable is None:
            raise AppServerError("Codex executable was not found.")
        self.executable: Path = executable
        self.timeout = timeout
        self._next_id = 1
        self._messages: queue.Queue[dict[str, Any] | BaseException | None] = queue.Queue()
        self._process = subprocess.Popen(
            [str(self.executable), "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None:
            self.close()
            raise AppServerError("Unable to open App Server stdio pipes.")
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "memova-codex-collector",
                    "title": "Memova Codex Collector",
                    "version": COLLECTOR_VERSION,
                },
                "capabilities": {
                    "experimentalApi": True,
                    "optOutNotificationMethods": [],
                },
            },
        )
        self.notify("initialized", {})

    def __enter__(self) -> JsonRpcAppServerClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    self._messages.put(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    self._messages.put(AppServerError(f"Invalid App Server JSON: {exc}"))
                    return
        except BaseException as exc:
            self._messages.put(exc)
        finally:
            self._messages.put(None)

    def _send(self, message: dict[str, Any]) -> None:
        if self._process.poll() is not None:
            raise AppServerError(f"App Server exited with code {self._process.returncode}.")
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._process.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        )
        while True:
            try:
                message = self._messages.get(timeout=self.timeout)
            except queue.Empty as exc:
                raise AppServerError(f"Timed out waiting for {method}.") from exc
            if message is None:
                raise AppServerError("App Server closed its output stream.")
            if isinstance(message, BaseException):
                raise AppServerError(str(message)) from message
            if message.get("id") != request_id:
                # Read-only collection does not need notifications or server-initiated requests.
                continue
            if "error" in message:
                raise AppServerError(f"{method} failed: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise AppServerError(f"{method} returned an invalid result.")
            return result

    def list_threads(self, *, archived: bool) -> list[dict[str, Any]]:
        threads: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            result = self.request(
                "thread/list",
                {
                    "archived": archived,
                    "cursor": cursor,
                    "limit": 100,
                    "sortKey": "updated_at",
                    "sortDirection": "desc",
                    "sourceKinds": list(ALLOWED_SOURCE_KINDS),
                },
            )
            data = result.get("data") or result.get("threads") or []
            if not isinstance(data, list):
                raise AppServerError("thread/list returned invalid data.")
            threads.extend(item for item in data if isinstance(item, dict))
            cursor_value = result.get("nextCursor") or result.get("next_cursor")
            cursor = cursor_value if isinstance(cursor_value, str) and cursor_value else None
            if cursor is None:
                break
        return threads

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        result = self.request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": True},
        )
        thread = result.get("thread", result)
        if not isinstance(thread, dict):
            raise AppServerError("thread/read returned an invalid thread.")
        return thread

    def close(self) -> None:
        process = getattr(self, "_process", None)
        if process is None or process.poll() is not None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
