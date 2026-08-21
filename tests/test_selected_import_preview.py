from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
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

    def test_default_stdout_is_human_readable_and_machine_record_is_private(self) -> None:
        text = "Q3 beta note with no credentials."
        original_stdin = MODULE.sys.stdin
        stdout = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                record_path = Path(temporary_directory) / "preview-record.json"
                MODULE.sys.stdin = io.TextIOWrapper(
                    io.BytesIO(text.encode("utf-8")), encoding="utf-8"
                )
                with redirect_stdout(stdout):
                    return_code = MODULE.main(
                        [
                            "--stdin",
                            "--selection-kind",
                            "excerpt",
                            "--source-label",
                            "Q3 beta note",
                            "--source-reference",
                            "current-chat:selected-excerpt",
                            "--record-file",
                            str(record_path),
                        ]
                    )

                self.assertEqual(return_code, 0)
                visible = stdout.getvalue()
                self.assertIn("Memova selected-content import preview", visible)
                self.assertIn(text, visible)
                self.assertIn("Nothing has been imported yet", visible)
                for internal_field in (
                    "preview_id",
                    "source_reference",
                    "sha256",
                    "scan_version",
                    "finding_counts_by_type",
                ):
                    self.assertNotIn(internal_field, visible)

                record = json.loads(record_path.read_text(encoding="utf-8"))
                self.assertIn("preview_id", record)
                self.assertEqual(record["source_reference"], "current-chat:selected-excerpt")
                self.assertEqual(record["sanitized_content"], text)
                self.assertEqual(record_path.stat().st_mode & 0o777, 0o600)
        finally:
            MODULE.sys.stdin = original_stdin


if __name__ == "__main__":
    unittest.main()
