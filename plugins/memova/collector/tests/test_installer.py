from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from memova_collector.ledger import Ledger
from memova_collector.contracts import CONSENT_SCHEMA_VERSION

MANAGER = (
    Path(__file__).parents[2]
    / "skills"
    / "memova-conversation-sync"
    / "scripts"
    / "manage_conversation_sync.py"
)


class InstallerTests(unittest.TestCase):
    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MANAGER), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_install_is_versioned_verified_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            install_root = Path(temp_dir) / "Memova Runtime"
            first = self._run("install", "--install-root", str(install_root), "--confirm")
            second = self._run("install", "--install-root", str(install_root), "--confirm")
            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            self.assertEqual(json.loads(first.stdout)["status"], "installed")
            self.assertEqual(json.loads(second.stdout)["status"], "already_current")
            current = json.loads((install_root / "current.json").read_text(encoding="utf-8"))
            runtime = Path(current["runtime"])
            self.assertTrue((runtime / "memova_collector" / "cli.py").exists())
            self.assertTrue((runtime / "manifest.json").exists())

    def test_scheduler_definition_requires_consent_live_preview_and_oauth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            install_root = root / "runtime"
            state_dir = install_root / "state"
            installed = self._run("install", "--install-root", str(install_root), "--confirm")
            self.assertEqual(installed.returncode, 0, installed.stdout)

            refused = self._run(
                "write-scheduler",
                "--install-root",
                str(install_root),
                "--home",
                str(root / "home"),
                "--platform",
                "linux",
                "--confirm",
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn("active consent", refused.stdout)

            state_dir.mkdir(parents=True)
            (state_dir / "consent.json").write_text(
                json.dumps({"schema_version": CONSENT_SCHEMA_VERSION, "status": "active"}),
                encoding="utf-8",
            )
            with Ledger(state_dir / "collector.sqlite3") as ledger:
                ledger.set_metadata("preview_source", "live")
                ledger.set_metadata("preview_completed_at", "2026-08-11T00:00:00Z")
            still_refused = self._run(
                "write-scheduler",
                "--install-root",
                str(install_root),
                "--home",
                str(root / "home"),
                "--platform",
                "linux",
                "--confirm",
            )
            self.assertEqual(still_refused.returncode, 2)
            self.assertIn("Memova OAuth", still_refused.stdout)

            uninstalled = self._run(
                "uninstall",
                "--install-root",
                str(install_root),
                "--confirm",
            )
            self.assertEqual(uninstalled.returncode, 0, uninstalled.stdout)
            archive = Path(json.loads(uninstalled.stdout)["archive"])
            self.assertTrue(archive.exists())
            self.assertFalse(install_root.exists())


if __name__ == "__main__":
    unittest.main()
