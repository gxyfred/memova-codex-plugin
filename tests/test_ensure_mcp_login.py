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
        self.assertEqual(captured[0]["status"], "oauth_present_scopes_unverified")
        self.assertEqual(
            captured[0]["scope_verification"], "unavailable_from_codex_mcp_list"
        )
        self.assertTrue(captured[0]["reauthorization_required_to_guarantee_scopes"])
        self.assertIsNone(captured[0]["ready_for_requested_workflow"])
        self.assertIn("Do not describe this state as workflow-ready", captured[0]["user_message"])

    def test_status_check_permission_denial_requires_normal_terminal_login(self) -> None:
        captured: list[dict] = []
        before = {
            "listed": False,
            "auth": None,
            "returncode": None,
            "raw": "",
            "error": "PermissionError: [Errno 1] Operation not permitted",
            "execution_denied": True,
        }
        with patch.object(
            ensure_mcp_login, "_mcp_status", return_value=before
        ), patch.object(ensure_mcp_login, "_run_login") as run_login, patch.object(
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
        ):
            return_code = ensure_mcp_login.main()

        self.assertEqual(return_code, 3)
        run_login.assert_not_called()
        self.assertEqual(captured[0]["status"], "manual_terminal_login_required")
        self.assertEqual(captured[0]["reason"], "local_codex_execution_denied")
        self.assertEqual(captured[0]["failure_stage"], "mcp_status_check")
        self.assertFalse(captured[0]["oauth_attempted"])
        self.assertFalse(captured[0]["browser_authorization_started"])
        self.assertEqual(
            captured[0]["manual_login_command"],
            "codex mcp login memova --scopes notes.read,personal_manual.write",
        )
        self.assertIn("outside the Codex task", captured[0]["recovery_hint"])

    def test_login_start_permission_denial_requires_normal_terminal_login(self) -> None:
        captured: list[dict] = []
        before = {
            "listed": True,
            "auth": "Not logged in",
            "returncode": 0,
            "raw": "memova Not logged in",
        }
        login = {
            "login_returncode": None,
            "opened_authorization_url": False,
            "timed_out": False,
            "login_error": "PermissionError: [Errno 1] Operation not permitted",
            "execution_denied": True,
            "failure_stage": "login_start",
        }
        with patch.object(
            ensure_mcp_login, "_mcp_status", return_value=before
        ) as mcp_status, patch.object(
            ensure_mcp_login, "_run_login", return_value=login
        ), patch.object(
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
        ):
            return_code = ensure_mcp_login.main()

        self.assertEqual(return_code, 3)
        mcp_status.assert_called_once()
        self.assertEqual(captured[0]["status"], "manual_terminal_login_required")
        self.assertEqual(captured[0]["failure_stage"], "login_start")
        self.assertTrue(captured[0]["oauth_attempted"])
        self.assertFalse(captured[0]["browser_authorization_started"])
        self.assertEqual(captured[0]["login"], login)

    def test_successful_login_with_denied_post_check_does_not_request_second_login(
        self,
    ) -> None:
        captured: list[dict] = []
        before = {
            "listed": True,
            "auth": "Not logged in",
            "returncode": 0,
            "raw": "memova Not logged in",
        }
        after = {
            "listed": False,
            "auth": None,
            "returncode": None,
            "raw": "",
            "error": "PermissionError: [Errno 1] Operation not permitted",
            "execution_denied": True,
        }
        login = {
            "login_returncode": 0,
            "opened_authorization_url": True,
            "timed_out": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            with patch.object(
                ensure_mcp_login,
                "_mcp_status",
                side_effect=[before, after],
            ), patch.object(
                ensure_mcp_login,
                "_run_login",
                return_value=login,
            ), patch.object(
                ensure_mcp_login,
                "_write_json",
                side_effect=captured.append,
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
        self.assertEqual(
            captured[0]["status"],
            "login_completed_client_refresh_required",
        )
        self.assertFalse(captured[0]["manual_login_required"])
        self.assertTrue(captured[0]["restart_or_new_task_required"])
        self.assertTrue(captured[0]["execution_denied"])
        self.assertEqual(captured[0]["failure_stage"], "post_login_status_check")
        self.assertIn("Do not log in again", captured[0]["recovery_hint"])
        self.assertEqual(
            state["requested_scopes"],
            ["notes.read", "personal_manual.write"],
        )

    def test_failed_login_with_denied_post_check_requires_manual_terminal_login(
        self,
    ) -> None:
        captured: list[dict] = []
        before = {
            "listed": True,
            "auth": "Not logged in",
            "returncode": 0,
            "raw": "memova Not logged in",
        }
        after = {
            "listed": False,
            "auth": None,
            "returncode": None,
            "raw": "Operation not permitted",
            "execution_denied": True,
        }
        login = {
            "login_returncode": 1,
            "opened_authorization_url": False,
            "timed_out": False,
        }
        with patch.object(
            ensure_mcp_login,
            "_mcp_status",
            side_effect=[before, after],
        ), patch.object(
            ensure_mcp_login,
            "_run_login",
            return_value=login,
        ), patch.object(
            ensure_mcp_login,
            "_write_json",
            side_effect=captured.append,
        ), patch.object(
            ensure_mcp_login.sys,
            "argv",
            [
                "ensure_mcp_login.py",
                "--recover-scopes",
                "--workflow",
                "personal-manual",
            ],
        ):
            return_code = ensure_mcp_login.main()

        self.assertEqual(return_code, 3)
        self.assertEqual(captured[0]["status"], "manual_terminal_login_required")
        self.assertEqual(captured[0]["failure_stage"], "post_login_status_check")

    def test_mcp_status_classifies_os_permission_denial(self) -> None:
        login_command = ensure_mcp_login.build_login_command(
            list(ensure_mcp_login.PERSONAL_MANUAL_SCOPES)
        )
        with patch.object(
            ensure_mcp_login.subprocess,
            "run",
            side_effect=PermissionError(1, "Operation not permitted"),
        ):
            status = ensure_mcp_login._mcp_status(login_command)

        self.assertFalse(status["listed"])
        self.assertTrue(status["execution_denied"])
        self.assertIn("Operation not permitted", status["error"])

    def test_run_login_classifies_os_permission_denial(self) -> None:
        login_command = ensure_mcp_login.build_login_command(
            list(ensure_mcp_login.PERSONAL_MANUAL_SCOPES)
        )
        with patch.object(
            ensure_mcp_login.subprocess,
            "Popen",
            side_effect=PermissionError(1, "Operation not permitted"),
        ):
            result = ensure_mcp_login._run_login(
                login_command=login_command,
                timeout_seconds=1,
            )

        self.assertTrue(result["execution_denied"])
        self.assertEqual(result["failure_stage"], "login_start")
        self.assertIn("outside the Codex task", result["recovery_hint"])

    def test_execution_denied_text_covers_eperm_and_eacces_messages(self) -> None:
        self.assertTrue(ensure_mcp_login._is_execution_denied_text("Operation not permitted"))
        self.assertTrue(ensure_mcp_login._is_execution_denied_text("Permission denied (os error 13)"))
        self.assertTrue(ensure_mcp_login._is_execution_denied_text("launcher failed: os error 1"))
        self.assertFalse(ensure_mcp_login._is_execution_denied_text("launcher failed: os error 10"))
        self.assertFalse(ensure_mcp_login._is_execution_denied_text("connection refused"))

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
