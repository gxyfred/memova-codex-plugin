from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
RENDERER = (
    ROOT
    / "plugins"
    / "memova"
    / "skills"
    / "memova-personal-manual"
    / "scripts"
    / "render_personal_manual.py"
)


class PersonalManualRendererTests(unittest.TestCase):
    def test_renderer_creates_only_matching_safe_deliverables(self) -> None:
        document = {
            "schema_version": "memova_personal_manual_document_v1",
            "language": "en",
            "title": "My <Manual>",
            "subtitle": "How I work",
            "overview": ["Evidence-led overview."],
            "sections": [
                {
                    "heading": "Collaboration",
                    "paragraphs": ["Prefer explicit contracts."],
                    "bullets": ["Confirm irreversible actions."],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            output = root / "output"
            source.write_text(json.dumps(document), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDERER),
                    "--input-json",
                    str(source),
                    "--output-dir",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            metadata = json.loads(result.stdout)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"personal-manual.md", "personal-manual.html"},
            )
            markdown = (output / "personal-manual.md").read_text(encoding="utf-8")
            html = (output / "personal-manual.html").read_text(encoding="utf-8")
            self.assertIn("# My <Manual>", markdown)
            self.assertIn("data-memova-personal-manual=\"v1\"", html)
            self.assertIn("My &lt;Manual&gt;", html)
            self.assertNotIn("<script", html.lower())
            self.assertEqual(
                Path(metadata["markdown_path"]),
                (output / "personal-manual.md").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
