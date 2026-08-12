from __future__ import annotations

import plistlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from memova_collector.scheduler import build_scheduler_plan


class SchedulerTests(unittest.TestCase):
    def _plan(self, system: str, root: Path):
        return build_scheduler_plan(
            system=system,
            home=root,
            state_dir=root / "state with spaces",
            python_executable=root / "Python With Spaces" / "python",
            launcher=root / "Memova" / "launcher.py",
        )

    def test_launchd_plan_is_valid_and_ignores_overlapping_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan("darwin", Path(temp_dir))
            content = next(iter(plan["files"].values())).encode("utf-8")
            payload = plistlib.loads(content)
            self.assertEqual(payload["StartInterval"], 900)
            self.assertEqual(payload["ProgramArguments"][2], "sync-once")
            self.assertTrue(plan["remote_upload_enabled"])
            self.assertEqual(plan["sink"], "memova-rest")
            self.assertIn("rest", payload["ProgramArguments"])

    def test_systemd_plan_uses_timer_and_quoted_exec_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan("linux", Path(temp_dir))
            values = "\n".join(plan["files"].values())
            self.assertIn("OnUnitActiveSec=900s", values)
            self.assertIn('ExecStart="', values)
            self.assertIn("Persistent=true", values)

    def test_windows_plan_is_valid_xml_and_ignores_overlaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan("windows", Path(temp_dir))
            content = next(iter(plan["files"].values()))
            ET.fromstring(content)
            self.assertIn("MultipleInstancesPolicy", content)
            self.assertIn("IgnoreNew", content)
            self.assertIn("PT15M", content)

    def test_refuses_too_frequent_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                build_scheduler_plan(
                    system="linux",
                    home=temp_dir,
                    state_dir=Path(temp_dir) / "state",
                    python_executable="python3",
                    launcher="launcher.py",
                    interval_seconds=60,
                )


if __name__ == "__main__":
    unittest.main()
