from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memova_collector.extraction import extract_thread

FIXTURES = Path(__file__).parent / "fixtures"


class ExtractionTests(unittest.TestCase):
    def test_collects_all_visible_messages_and_excludes_sensitive_items(self) -> None:
        payload = json.loads((FIXTURES / "app-server-history-v1.json").read_text())
        thread, diagnostics = extract_thread(
            payload["threads"]["thread-active-001"],
            archived=False,
        )

        self.assertEqual(len(thread["messages"]), 5)
        self.assertEqual(
            [message["phase"] for message in thread["messages"]],
            [None, "commentary", None, "commentary", "final_answer"],
        )
        encoded = json.dumps(thread, ensure_ascii=False)
        self.assertNotIn("TOKEN=secret", encoded)
        self.assertNotIn("reasoning-secret", encoded)
        self.assertNotIn("/secret.txt", encoded)
        self.assertNotIn("/private/example.png", encoded)
        self.assertEqual(diagnostics["excluded_reasoning"], 1)
        self.assertEqual(diagnostics["excluded_commandExecution"], 1)
        self.assertEqual(diagnostics["excluded_fileChange"], 1)
        self.assertEqual(diagnostics["excluded_non_text_part"], 1)

    def test_project_context_is_stable_and_never_exports_paths_or_remote_urls(self) -> None:
        payload = json.loads((FIXTURES / "app-server-history-v1.json").read_text())
        with tempfile.TemporaryDirectory(prefix="memova-project-context-") as temp_dir:
            repository = Path(temp_dir) / "private-user" / "memova"
            working_directory = repository / "app" / "services"
            working_directory.mkdir(parents=True)
            (repository / ".git").mkdir()
            source = {
                **payload["threads"]["thread-active-001"],
                "cwd": str(working_directory),
                "gitInfo": {
                    "branch": "codex/collector-backend",
                    "originUrl": "https://token@example.test/private/memova.git?secret=yes",
                    "sha": "deadbeef",
                },
            }

            first, _ = extract_thread(
                source,
                archived=False,
                project_fingerprint_secret="device-private-secret",
                workspace_repository_fingerprint_key="a" * 64,
            )
            replay, _ = extract_thread(
                source,
                archived=False,
                project_fingerprint_secret="device-private-secret",
                workspace_repository_fingerprint_key="a" * 64,
            )
            other_device, _ = extract_thread(
                source,
                archived=False,
                project_fingerprint_secret="other-device-secret",
                workspace_repository_fingerprint_key="a" * 64,
            )
            other_workspace, _ = extract_thread(
                source,
                archived=False,
                project_fingerprint_secret="device-private-secret",
                workspace_repository_fingerprint_key="b" * 64,
            )

        context = first["project_context"]
        encoded = json.dumps(first, ensure_ascii=False)
        self.assertEqual(first, replay)
        self.assertEqual(
            context["repository_fingerprint"],
            other_device["project_context"]["repository_fingerprint"],
        )
        self.assertNotEqual(
            context["repository_fingerprint"],
            other_workspace["project_context"]["repository_fingerprint"],
        )
        self.assertEqual(context["repository_identity_kind"], "workspace_hmac_remote")
        self.assertEqual(context["repository_display_name"], "memova")
        self.assertEqual(context["branch"], "codex/collector-backend")
        self.assertEqual(context["working_path"], "app/services")
        self.assertNotIn(temp_dir, encoded)
        self.assertNotIn("token@example.test", encoded)
        self.assertNotIn("deadbeef", encoded)
        self.assertNotIn("originUrl", encoded)

    def test_malformed_remote_fails_closed_to_local_opaque_identity(self) -> None:
        payload = json.loads((FIXTURES / "app-server-history-v1.json").read_text())
        with tempfile.TemporaryDirectory(prefix="memova-project-context-") as temp_dir:
            repository = Path(temp_dir) / "memova"
            repository.mkdir()
            (repository / ".git").mkdir()
            source = {
                **payload["threads"]["thread-active-001"],
                "cwd": str(repository),
                "gitInfo": {"originUrl": "https://example.test:invalid/private.git"},
            }
            thread, _ = extract_thread(
                source,
                archived=False,
                project_fingerprint_secret="device-private-secret",
            )

        context = thread["project_context"]
        self.assertEqual(context["repository_display_name"], "memova")
        self.assertEqual(context["working_path"], ".")
        self.assertNotIn("example.test", json.dumps(context))


if __name__ == "__main__":
    unittest.main()
