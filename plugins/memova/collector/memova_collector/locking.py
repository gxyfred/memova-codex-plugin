from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


class CollectorAlreadyRunningError(RuntimeError):
    """Raised when a second scheduled or manual sync overlaps an active run."""


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock(path: str | Path) -> dict[str, Any] | None:
    lock_path = Path(path)
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


class RunLock:
    def __init__(self, path: str | Path, *, stale_after_seconds: int = 3600) -> None:
        self.path = Path(path)
        self.stale_after_seconds = stale_after_seconds
        self.token = str(uuid.uuid4())
        self.acquired = False

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    def _can_reclaim(self) -> bool:
        payload = read_lock(self.path)
        if payload is None:
            try:
                age = time.time() - self.path.stat().st_mtime
            except FileNotFoundError:
                return True
            return age > self.stale_after_seconds
        acquired_epoch = float(payload.get("acquired_epoch") or 0)
        pid = int(payload.get("pid") or 0)
        return (
            time.time() - acquired_epoch > self.stale_after_seconds
            and not _pid_is_running(pid)
        )

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError as exc:
                if attempt == 0 and self._can_reclaim():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise CollectorAlreadyRunningError(
                    f"A Collector run is already active ({self.path}).",
                ) from exc
            payload = {
                "pid": os.getpid(),
                "token": self.token,
                "acquired_epoch": time.time(),
            }
            try:
                os.write(descriptor, json.dumps(payload, sort_keys=True).encode("utf-8"))
            finally:
                os.close(descriptor)
            self.acquired = True
            return
        raise CollectorAlreadyRunningError(f"Could not acquire Collector lock ({self.path}).")

    def release(self) -> None:
        if not self.acquired:
            return
        payload = read_lock(self.path)
        if payload is not None and payload.get("token") == self.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.acquired = False
