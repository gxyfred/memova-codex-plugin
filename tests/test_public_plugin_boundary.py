from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "memova"


class PublicPluginBoundaryTests(unittest.TestCase):
    def test_public_plugin_skill_catalog_matches_current_menu(self) -> None:
        skill_names = {
            path.parent.name for path in (PLUGIN / "skills").glob("*/SKILL.md")
        }
        self.assertEqual(
            skill_names,
            {
                "memova-menu",
                "memova-knowledge",
                "memova-explicit-import",
                "memova-workflow",
                "memova-vault-setup",
                "memova-vault-diagnose",
            },
        )

        menu = (PLUGIN / "skills" / "memova-menu" / "SKILL.md").read_text(encoding="utf-8")
        for option in (
            "1. Search and use my Knowledge V5",
            "2. Propose a Knowledge V5 update",
            "3. Import selected content",
            "4. Review my automation tasks",
            "5. Run latest note automation tasks",
            "6. Legacy V2/V3 vault setup or diagnosis",
        ):
            self.assertIn(option, menu)

    def test_public_plugin_does_not_bundle_collector_or_hooks(self) -> None:
        self.assertFalse((PLUGIN / "collector").exists())
        self.assertFalse((PLUGIN / "hooks").exists())
        self.assertFalse((PLUGIN / "skills" / "memova-conversation-sync").exists())
        manifest = json.loads(
            (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("hooks", manifest)
        self.assertEqual(manifest["version"], "1.6.1")

    def test_public_mcp_login_cannot_request_collector_pairing_scope(self) -> None:
        helper = (PLUGIN / "scripts" / "ensure_mcp_login.py").read_text(encoding="utf-8")
        self.assertNotIn("conversations.connect", helper)
        self.assertNotIn("include-conversation-connect", helper)
        self.assertNotIn('"actions.read"', helper)
        self.assertNotIn('"actions.write"', helper)

    def test_latest_note_skill_uses_the_deployed_statuses_argument(self) -> None:
        workflow = (PLUGIN / "skills" / "memova-workflow" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('statuses=["pending","running"]', workflow)
        self.assertNotIn('status=["pending","running"]', workflow)

    def test_workflow_skill_is_discoverable_for_natural_language_task_reviews(self) -> None:
        workflow = (PLUGIN / "skills" / "memova-workflow" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        openai_yaml = (
            PLUGIN / "skills" / "memova-workflow" / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn("list unfinished tasks", workflow)
        self.assertIn("waiting for confirmation", workflow)
        self.assertIn("Preserve waiting_for_user as guarded", workflow)
        self.assertIn("allow_implicit_invocation: true", openai_yaml)

    def test_public_user_facing_metadata_does_not_advertise_collector(self) -> None:
        paths = (
            PLUGIN / ".codex-plugin" / "plugin.json",
            PLUGIN / ".mcp.json",
            PLUGIN / "skills" / "memova-menu" / "SKILL.md",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertNotIn("collector", path.read_text(encoding="utf-8").lower())

    def test_manifest_exposes_at_most_three_default_prompts(self) -> None:
        manifest = json.loads(
            (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        prompts = manifest["interface"]["defaultPrompt"]
        self.assertLessEqual(len(prompts), 3)
        self.assertIn("Import selected content into Memova.", prompts)

    def test_user_facing_skills_hide_internal_audit_fields_by_default(self) -> None:
        explicit_import = (
            PLUGIN / "skills" / "memova-explicit-import" / "SKILL.md"
        ).read_text(encoding="utf-8")
        workflow = (PLUGIN / "skills" / "memova-workflow" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        menu = (PLUGIN / "skills" / "memova-menu" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Do not show preview ids", explicit_import)
        self.assertIn("Hard user-interface boundary", explicit_import)
        self.assertIn("Treat accidental exposure of any such field as a failed preview", explicit_import)
        self.assertIn("do not call the import tool", explicit_import)
        self.assertIn("technical preview fields to the MCP tool unchanged", explicit_import)
        self.assertIn("Keep task, note, meeting, action, lease", workflow)
        self.assertIn("Keep internal ids, claim tokens, hashes", workflow)
        self.assertIn("Treat `waiting_for_user` as requiring user attention", workflow)
        self.assertIn("does not turn a `waiting_for_user` task into an approved", workflow)
        self.assertIn("answer **No — it", workflow)
        self.assertIn("is waiting for the user**", workflow)
        self.assertIn("Never describe any part of a `waiting_for_user` task as currently", workflow)
        self.assertIn("not permission to proceed", workflow)
        self.assertIn("machine provenance/version tags", workflow)
        self.assertIn("synthetic Memova data", workflow)
        self.assertIn("Keep internal ids", menu)

        self.assertNotIn("summarize the task ids", workflow.lower())
        self.assertNotIn("Summarize task ids", menu)


if __name__ == "__main__":
    unittest.main()
