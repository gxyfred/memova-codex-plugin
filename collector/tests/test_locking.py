from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from memova_collector.locking import CollectorAlreadyRunningError, RunLock


class LockingTests(unittest.TestCase):
    def test_second_run_cannot_overlap_active_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sync.lock"
            with RunLock(path):
                with self.assertRaises(CollectorAlreadyRunningError):
                    RunLock(path).acquire()
            self.assertFalse(path.exists())

    def test_dead_stale_lock_is_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sync.lock"
            path.write_text(
                json.dumps(
                    {
                        "pid": 999_999_999,
                        "token": "dead-run",
                        "acquired_epoch": time.time() - 7200,
                    },
                ),
                encoding="utf-8",
            )
            with RunLock(path, stale_after_seconds=3600):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["pid"], os.getpid())


if __name__ == "__main__":
    unittest.main()
