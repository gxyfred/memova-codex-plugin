from __future__ import annotations

import importlib.util
import io
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "plugins"
    / "memova"
    / "skills"
    / "memova-explicit-import"
    / "scripts"
    / "preview_selected_import.py"
)
SPEC = importlib.util.spec_from_file_location("preview_selected_import", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SelectedImportPreviewTests(unittest.TestCase):
    def test_restricted_values_are_replaced_without_being_returned(self) -> None:
        secret = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"
        text = f"ordinary text\napi_key={secret}\nAuthorization: Bearer abcdefghijklmnop"
        sanitized, findings = MODULE.sanitize_text(text)
        self.assertNotIn(secret, sanitized)
        self.assertNotIn("abcdefghijklmnop", sanitized)
        self.assertIn("[REDACTED:", sanitized)
        self.assertGreaterEqual(sum(findings.values()), 2)

    def test_non_secret_text_is_byte_stable(self) -> None:
        text = "会议结论：下周发布。\nNo credentials are included."
        sanitized, findings = MODULE.sanitize_text(text)
        self.assertEqual(sanitized, text)
        self.assertEqual(sum(findings.values()), 0)

    def test_stdin_size_limit_is_enforced(self) -> None:
        args = type("Args", (), {"stdin": True, "input_file": None})()
        original_stdin = MODULE.sys.stdin
        try:
            MODULE.sys.stdin = io.TextIOWrapper(
                io.BytesIO(b"x" * (MODULE.MAX_INPUT_BYTES + 1)), encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                MODULE._read_input(args)
        finally:
            MODULE.sys.stdin = original_stdin


if __name__ == "__main__":
    unittest.main()
