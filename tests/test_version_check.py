from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "plugins" / "memova" / "scripts" / "version_check.py"
SPEC = importlib.util.spec_from_file_location("memova_version_check", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
version_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(version_check)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class VersionCheckTests(unittest.TestCase):
    def test_fetches_backend_owned_compatibility_contract(self) -> None:
        response = _Response(
            {
                "schema_version": "memova_plugin_compatibility_v1",
                "plugin_name": "memova",
                "latest_version": "1.9.1",
                "minimum_supported_version": "1.8.2",
            },
        )

        with patch.object(version_check.urllib.request, "urlopen", return_value=response) as urlopen:
            compatibility = version_check.fetch_compatibility("https://api.example.test/compat")

        self.assertEqual(
            compatibility,
            {"latest_version": "1.9.1", "minimum_supported_version": "1.8.2"},
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/compat")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 4)

    def test_rejects_an_unversioned_or_wrong_plugin_response(self) -> None:
        invalid_payloads = (
            {
                "plugin_name": "memova",
                "latest_version": "1.9.1",
                "minimum_supported_version": "1.8.2",
            },
            {
                "schema_version": "memova_plugin_compatibility_v1",
                "plugin_name": "another-plugin",
                "latest_version": "1.9.1",
                "minimum_supported_version": "1.8.2",
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with patch.object(
                    version_check.urllib.request,
                    "urlopen",
                    return_value=_Response(payload),
                ):
                    with self.assertRaises(ValueError):
                        version_check.fetch_compatibility("https://api.example.test/compat")

    def test_uses_daily_network_cache_and_falls_back_to_it_on_failure(self) -> None:
        now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
        state = {
            "compatibility_url": "https://api.example.test/compat",
            "latest_version": "1.9.1",
            "minimum_supported_version": "1.8.2",
            "last_checked_at": version_check.to_iso(now - timedelta(hours=2)),
        }

        with patch.object(version_check, "fetch_compatibility") as fetch:
            compatibility, source, skipped, error = version_check.resolve_compatibility(
                state=state,
                compatibility_url="https://api.example.test/compat",
                now=now,
                force=False,
            )

        fetch.assert_not_called()
        self.assertEqual(compatibility["latest_version"], "1.9.1")
        self.assertEqual((source, skipped, error), ("cache", "check_interval_not_elapsed", None))

        state["last_checked_at"] = version_check.to_iso(now - timedelta(days=2))
        with patch.object(version_check, "fetch_compatibility", side_effect=OSError("offline")):
            compatibility, source, skipped, error = version_check.resolve_compatibility(
                state=state,
                compatibility_url="https://api.example.test/compat",
                now=now,
                force=False,
            )

        self.assertEqual(compatibility["latest_version"], "1.9.1")
        self.assertEqual((source, skipped), ("cache", "latest_check_failed"))
        self.assertIn("offline", error)

    def test_recent_failed_check_is_throttled_even_without_cached_metadata(self) -> None:
        now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
        state = {
            "compatibility_url": "https://api.example.test/compat",
            "last_checked_at": version_check.to_iso(now - timedelta(minutes=5)),
        }

        with patch.object(version_check, "fetch_compatibility") as fetch:
            compatibility, source, skipped, error = version_check.resolve_compatibility(
                state=state,
                compatibility_url="https://api.example.test/compat",
                now=now,
                force=False,
            )

        fetch.assert_not_called()
        self.assertIsNone(compatibility)
        self.assertEqual((source, skipped, error), ("cache", "check_interval_not_elapsed", None))

    def test_same_latest_version_reminds_at_most_once_per_day(self) -> None:
        now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
        state = {}

        self.assertTrue(
            version_check.should_show_update_reminder(
                state=state,
                latest_version="1.9.1",
                update_available=True,
                now=now,
            ),
        )

        state.update(
            {
                "last_reminded_version": "1.9.1",
                "last_reminded_at": version_check.to_iso(now - timedelta(hours=23)),
            },
        )
        self.assertFalse(
            version_check.should_show_update_reminder(
                state=state,
                latest_version="1.9.1",
                update_available=True,
                now=now,
            ),
        )

        state["last_reminded_at"] = version_check.to_iso(now - timedelta(hours=24))
        self.assertTrue(
            version_check.should_show_update_reminder(
                state=state,
                latest_version="1.9.1",
                update_available=True,
                now=now,
            ),
        )

    def test_semver_comparison_does_not_treat_prerelease_as_newer_than_release(self) -> None:
        self.assertTrue(version_check.is_newer_version("1.9.1", "1.9.0"))
        self.assertTrue(version_check.is_newer_version("1.9.1", "1.9.1-rc.1"))
        self.assertFalse(version_check.is_newer_version("1.9.1-rc.1", "1.9.1"))
        self.assertFalse(version_check.is_newer_version("not-a-version", "1.9.0"))


if __name__ == "__main__":
    unittest.main()
