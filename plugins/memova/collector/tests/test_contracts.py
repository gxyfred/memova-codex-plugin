from __future__ import annotations

import json
import unittest
from pathlib import Path

from memova_collector.contracts import BATCH_SCHEMA_VERSION, COLLECTOR_VERSION, build_batch


class ContractTests(unittest.TestCase):
    def test_all_json_schemas_parse_and_have_ids(self) -> None:
        schema_dir = Path(__file__).parents[1] / "schemas"
        schemas = sorted(schema_dir.glob("*.schema.json"))
        # Collector owns only neutral archive transport contracts; the former
        # Knowledge V3 adapter schema intentionally no longer ships here.
        self.assertEqual(len(schemas), 7)
        for path in schemas:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("$schema", payload, path.name)
            self.assertIn("$id", payload, path.name)
            self.assertIn("title", payload, path.name)

    def test_collector_emits_the_v2_archive_contract(self) -> None:
        batch = build_batch(
            consent_id="consent-0001",
            device_id="device-0001",
            delivery_target="rest",
            threads=[],
        )

        self.assertEqual(BATCH_SCHEMA_VERSION, "memova_external_conversation_batch_v2")
        self.assertEqual(COLLECTOR_VERSION, "1.2.0")
        self.assertEqual(batch["schema_version"], BATCH_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
