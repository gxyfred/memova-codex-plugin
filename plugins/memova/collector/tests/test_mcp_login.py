from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "ensure_mcp_login.py"
SPEC = importlib.util.spec_from_file_location("ensure_mcp_login", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class McpLoginHelperTests(unittest.TestCase):
    def test_conversation_pairing_scope_is_requested_with_existing_base_scopes(self) -> None:
        command = MODULE.build_login_command(
            [*MODULE.BASE_SCOPES, MODULE.CONVERSATION_CONNECT_SCOPE]
        )
        self.assertEqual(command[:4], ["codex", "mcp", "login", "memova"])
        scopes = command[5].split(",")
        self.assertEqual(scopes[-1], "conversations.connect")
        self.assertTrue(set(MODULE.BASE_SCOPES).issubset(scopes))
        self.assertIn("knowledge.read", scopes)
        self.assertIn("knowledge.write", scopes)

    def test_scope_validation_rejects_shell_or_whitespace_payloads(self) -> None:
        for invalid in ("notes.read --evil", "$(command)", "", "notes read"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                MODULE.build_login_command([invalid])


if __name__ == "__main__":
    unittest.main()
