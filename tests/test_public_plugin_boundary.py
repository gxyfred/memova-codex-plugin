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


if __name__ == "__main__":
    unittest.main()
