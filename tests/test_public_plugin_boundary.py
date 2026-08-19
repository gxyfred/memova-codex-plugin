from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "memova"


class PublicPluginBoundaryTests(unittest.TestCase):
    def test_public_plugin_does_not_bundle_collector_or_hooks(self) -> None:
        self.assertFalse((PLUGIN / "collector").exists())
        self.assertFalse((PLUGIN / "hooks").exists())
        self.assertFalse((PLUGIN / "skills" / "memova-conversation-sync").exists())
        manifest = json.loads(
            (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("hooks", manifest)
        self.assertEqual(manifest["version"], "1.6.0")

    def test_public_mcp_login_cannot_request_collector_pairing_scope(self) -> None:
        helper = (PLUGIN / "scripts" / "ensure_mcp_login.py").read_text(encoding="utf-8")
        self.assertNotIn("conversations.connect", helper)
        self.assertNotIn("include-conversation-connect", helper)

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
