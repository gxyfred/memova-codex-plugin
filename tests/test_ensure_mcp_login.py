from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "plugins" / "memova" / "scripts" / "ensure_mcp_login.py"
SPEC = importlib.util.spec_from_file_location("memova_ensure_mcp_login", SCRIPT_PATH)
assert SPEC and SPEC.loader
ensure_mcp_login = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ensure_mcp_login)


class EnsureMcpLoginTests(unittest.TestCase):
    def test_personal_manual_login_requests_only_minimum_scopes(self) -> None:
        command = ensure_mcp_login.build_login_command(
            list(ensure_mcp_login.PERSONAL_MANUAL_SCOPES)
        )

        self.assertEqual(
            command,
            [
                "codex",
                "mcp",
                "login",
                "memova",
                "--scopes",
                "notes.read,personal_manual.write",
            ],
        )

    def test_existing_oauth_does_not_claim_requested_scopes_are_verified(self) -> None:
        captured: list[dict] = []
        status = {"listed": True, "auth": "OAuth", "returncode": 0, "raw": "memova OAuth"}
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            ensure_mcp_login, "_mcp_status", return_value=status
        ), patch.object(ensure_mcp_login, "_write_json", side_effect=captured.append), patch.object(
            ensure_mcp_login.sys,
            "argv",
            ["ensure_mcp_login.py", "--workflow", "personal-manual"],
        ), patch.dict(
            ensure_mcp_login.os.environ,
            {"MEMOVA_MCP_SCOPE_RECOVERY_STATE_PATH": str(Path(temporary) / "state.json")},
        ):
            return_code = ensure_mcp_login.main()

        self.assertEqual(return_code, 0)
        self.assertEqual(captured[0]["status"], "already_logged_in")
        self.assertEqual(
            captured[0]["scope_verification"], "unavailable_from_codex_mcp_list"
        )
        self.assertTrue(captured[0]["reauthorization_required_to_guarantee_scopes"])

    def test_scope_recovery_runs_oauth_and_records_success(self) -> None:
        captured: list[dict] = []
        status = {"listed": True, "auth": "OAuth", "returncode": 0, "raw": "memova OAuth"}
        login_result = {
            "login_returncode": 0,
            "opened_authorization_url": True,
            "timed_out": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            with patch.object(ensure_mcp_login, "_mcp_status", return_value=status), patch.object(
                ensure_mcp_login, "_run_login", return_value=login_result
            ) as run_login, patch.object(
                ensure_mcp_login, "_write_json", side_effect=captured.append
            ), patch.object(
                ensure_mcp_login.sys,
                "argv",
                [
                    "ensure_mcp_login.py",
                    "--recover-scopes",
                    "--workflow",
                    "personal-manual",
                ],
            ), patch.dict(
                ensure_mcp_login.os.environ,
                {"MEMOVA_MCP_SCOPE_RECOVERY_STATE_PATH": str(state_path)},
            ):
                return_code = ensure_mcp_login.main()

            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(return_code, 0)
        run_login.assert_called_once()
        self.assertEqual(captured[0]["status"], "login_completed")
        self.assertTrue(captured[0]["restart_or_new_task_required"])
        self.assertEqual(state["requested_scopes"], ["notes.read", "personal_manual.write"])

    def test_recent_scope_recovery_prevents_an_oauth_loop(self) -> None:
        captured: list[dict] = []
        status = {"listed": True, "auth": "OAuth", "returncode": 0, "raw": "memova OAuth"}
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            ensure_mcp_login.write_scope_recovery_state(
                state_path,
                requested_scopes=list(ensure_mcp_login.PERSONAL_MANUAL_SCOPES),
                completed_at=datetime.now(timezone.utc),
            )
            with patch.object(ensure_mcp_login, "_mcp_status", return_value=status), patch.object(
                ensure_mcp_login, "_run_login"
            ) as run_login, patch.object(
                ensure_mcp_login, "_write_json", side_effect=captured.append
            ), patch.object(
                ensure_mcp_login.sys,
                "argv",
                [
                    "ensure_mcp_login.py",
                    "--recover-scopes",
                    "--workflow",
                    "personal-manual",
                ],
            ), patch.dict(
                ensure_mcp_login.os.environ,
                {"MEMOVA_MCP_SCOPE_RECOVERY_STATE_PATH": str(state_path)},
            ):
                return_code = ensure_mcp_login.main()

        self.assertEqual(return_code, 0)
        run_login.assert_not_called()
        self.assertEqual(
            captured[0]["status"], "recent_scope_recovery_requires_client_refresh"
        )
        self.assertFalse(captured[0]["oauth_attempted"])

    def test_expired_scope_recovery_does_not_block_a_retry(self) -> None:
        now = datetime.now(timezone.utc)
        state = {
            "requested_scopes": list(ensure_mcp_login.PERSONAL_MANUAL_SCOPES),
            "completed_at": ensure_mcp_login._format_timestamp(
                now - ensure_mcp_login.SCOPE_RECOVERY_COOLDOWN - timedelta(seconds=1)
            ),
        }

        self.assertFalse(
            ensure_mcp_login.recently_recovered_scopes(
                state,
                requested_scopes=list(ensure_mcp_login.PERSONAL_MANUAL_SCOPES),
                now=now,
            )
        )


if __name__ == "__main__":
    unittest.main()
