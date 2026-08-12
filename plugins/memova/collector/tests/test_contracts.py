from __future__ import annotations

import json
import unittest
from pathlib import Path


class ContractTests(unittest.TestCase):
    def test_all_json_schemas_parse_and_have_ids(self) -> None:
        schema_dir = Path(__file__).parents[1] / "schemas"
        schemas = sorted(schema_dir.glob("*.schema.json"))
        # Collector owns only neutral archive transport contracts; the former
        # Knowledge V3 adapter schema intentionally no longer ships here.
        self.assertEqual(len(schemas), 6)
        for path in schemas:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("$schema", payload, path.name)
            self.assertIn("$id", payload, path.name)
            self.assertIn("title", payload, path.name)


if __name__ == "__main__":
    unittest.main()
