from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_multiplatform_soak.py"
SPEC = importlib.util.spec_from_file_location("run_multiplatform_soak", SCRIPT)
assert SPEC and SPEC.loader
soak = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(soak)


class _CredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, account: str) -> str | None:
        return self.values.get(account)

    def set(self, account: str, secret: str) -> None:
        self.values[account] = secret

    def delete(self, account: str) -> None:
        self.values.pop(account, None)


class MultiplatformSoakTests(unittest.TestCase):
    def test_restart_soak_recovers_outbox_and_reaches_idempotent_noop(self) -> None:
        with patch.object(soak, "system_credential_store", return_value=_CredentialStore()):
            result = soak.run_soak(
                cycles=12,
                interval_seconds=0,
                device_id="test-native-device",
            )
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["synthetic_content_only"])
        self.assertFalse(result["remote_upload_performed"])
        self.assertGreaterEqual(result["no_op_cycles"], 1)


if __name__ == "__main__":
    unittest.main()
