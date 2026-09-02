from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PREPARER = (
    ROOT
    / "plugins"
    / "memova"
    / "skills"
    / "memova-personal-manual"
    / "scripts"
    / "prepare_personal_manual.py"
)
PERSONAL_MANUAL_SKILL = (
    ROOT
    / "plugins"
    / "memova"
    / "skills"
    / "memova-personal-manual"
    / "SKILL.md"
)
LOCAL_ARTIFACTS = PERSONAL_MANUAL_SKILL.parent / "references" / "local-artifacts.md"
WORK_ARCHETYPES = (
    "The Refiner",
    "The Maker",
    "The Scout",
    "The Pathfinder",
    "The Builder",
    "The Curator",
    "The Cartographer",
    "The Visionary",
    "The Listener",
    "The Improviser",
    "The Forager",
    "The Explorer",
    "The Examiner",
    "The Guide",
    "The Gatherer",
    "The Conductor",
)
DISCLAIMER = (
    "These results describe patterns visible in your available AI conversations. They may change "
    "across roles, tasks, and periods of life, and you can correct any interpretation that does "
    "not fit."
)

MANUAL = f"""Work Archetype: The Conductor
Output Language: en
1. How I Operate
How I think
I test the frame before I settle it.
How I read
I prefer structure and evidence.
How I write
I refine through contrast.
2. What Moves and Grounds Me
What gives me energy
- Turning ambiguity into direction.
What I care about
- Protecting human dignity.
3. Relationships and Collaboration
How I communicate
I give context and name the outcome.
How to work with me
- Present a recommendation and tradeoff.
People that help me thrive
Grounded, Candid, Perceptive, Dependable, Independent
People who challenge assumptions constructively.
Environments that help me thrive
Autonomy, Continuity, Rigor, Humanity, Momentum
Places with autonomy and follow-through.
4. What Makes Me Distinctive
My strengths
I connect human meaning and implementation detail.
Current growth edge
Release smaller reversible versions sooner.
Internal conflicts
- I value exploration and stable conclusions.
5. Moving Forward
The person I am trying to become
I am pairing range with deliberate closure.
Advice from Memova
- Record the threshold and next signal.
- Record what materially improved.
{DISCLAIMER}
"""


class PersonalManualPreparerTests(unittest.TestCase):
    def test_skill_proves_readiness_and_loads_current_contract_before_history(self) -> None:
        skill = PERSONAL_MANUAL_SKILL.read_text(encoding="utf-8")

        preflight = skill.index("call `get_personal_manual_preflight`")
        contract = skill.index("call `get_current_personal_manual_generation_contract`")
        history = skill.index("## Read the bounded history locally")

        self.assertLess(preflight, contract)
        self.assertLess(contract, history)
        self.assertIn("contract_version=personal_manual_generation_v6", skill)
        self.assertIn("upload_tool=upsert_personal_manual", skill)
        self.assertIn("at most 20 total evidence items", skill)
        self.assertIn("do not loop, use a local contract copy", " ".join(skill.split()))
        self.assertTrue(LOCAL_ARTIFACTS.exists())
        artifact_contract = LOCAL_ARTIFACTS.read_text(encoding="utf-8")
        self.assertIn(
            "source_name,source_kind,item_count,visible_text_unit_count,status",
            artifact_contract,
        )
        self.assertNotIn("source_type,conversation_count,turn_count,status", artifact_contract)
        self.assertFalse((LOCAL_ARTIFACTS.parent / "generation-prompt.md").exists())

    def test_preparer_emits_markdown_local_csvs_and_minimal_upload_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manual = root / "raw.md"
            scores = root / "scores.csv"
            sources = root / "sources.csv"
            output = root / "output"
            manual.write_text(MANUAL, encoding="utf-8")
            _write_csv(
                scores,
                ["category", "key", "value", "confidence"],
                [
                    ["archetype", "work_archetype", "The Conductor", ""],
                    ["dimension", "dimension_1", "63", "0.8"],
                    ["dimension", "dimension_2", "63", "0.8"],
                    ["dimension", "dimension_3", "56", "0.7"],
                    ["dimension", "dimension_4", "74", "0.9"],
                    ["overall", "archetype_confidence", "84", ""],
                    ["facet", "Gregariousness", "61", "0.6"],
                ],
            )
            _write_csv(
                sources,
                [
                    "source_name",
                    "source_kind",
                    "item_count",
                    "visible_text_unit_count",
                    "status",
                ],
                [["Codex", "conversation_history", "20", "180", "available"]],
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PREPARER),
                    "--manual-md",
                    str(manual),
                    "--scores-csv",
                    str(scores),
                    "--sources-csv",
                    str(sources),
                    "--output-dir",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {
                    "personal-manual.md",
                    "personal-manual-scores.csv",
                    "personal-manual-sources.csv",
                    "personal-manual-upload.json",
                },
            )
            payload = json.loads((output / "personal-manual-upload.json").read_text())
            self.assertEqual(payload["schema_version"], "personal_manual_v1")
            self.assertEqual(payload["document"]["language_code"], "en")
            self.assertEqual(payload["document"]["dimension_scores"]["dimension_4"], 74)
            self.assertEqual(
                payload["document"]["manual"]["people_that_help_me_thrive"],
                "People who challenge assumptions constructively.",
            )
            self.assertEqual(
                payload["document"]["manual"]["people_keywords"],
                ["Grounded", "Candid", "Perceptive", "Dependable", "Independent"],
            )
            self.assertEqual(
                payload["document"]["manual"]["environment_keywords"],
                ["Autonomy", "Continuity", "Rigor", "Humanity", "Momentum"],
            )
            audit = payload["private_metadata"]["personal_manual_audit"]
            self.assertEqual(audit["format_version"], "personal_manual_audit_csv_v2")
            self.assertIn("facet,Gregariousness,61,0.6", audit["scores_csv"])
            self.assertEqual(audit["scores_csv"], _read_raw(scores))
            self.assertEqual(audit["sources_csv"], _read_raw(sources))
            self.assertNotIn("html_content", payload)
            self.assertNotIn("upload_confirmed", payload)
            self.assertEqual(
                payload["private_metadata"]["generation_contract_version"],
                "personal_manual_generation_v6",
            )
            self.assertNotIn("source_statistics", payload["private_metadata"])
            self.assertEqual(
                payload["private_metadata"]["evidence_sources"],
                [
                    {
                        "source_name": "Codex",
                        "source_kind": "conversation_history",
                        "item_count": 20,
                        "visible_text_unit_count": 180,
                        "status": "available",
                    }
                ],
            )

    def test_preparer_rejects_false_unavailable_evidence_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manual = root / "manual.md"
            scores = root / "scores.csv"
            sources = root / "sources.csv"
            manual.write_text(MANUAL, encoding="utf-8")
            _write_csv(
                scores,
                ["category", "key", "value", "confidence"],
                [
                    ["archetype", "work_archetype", "The Conductor", ""],
                    *[["dimension", f"dimension_{index}", "50", "0.5"] for index in range(1, 5)],
                    ["overall", "archetype_confidence", "50", ""],
                    ["facet", "Ideas", "50", "0.5"],
                ],
            )
            _write_csv(
                sources,
                [
                    "source_name",
                    "source_kind",
                    "item_count",
                    "visible_text_unit_count",
                    "status",
                ],
                [["Codex", "conversation_history", "1", "2", "unavailable"]],
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PREPARER),
                    "--manual-md",
                    str(manual),
                    "--scores-csv",
                    str(scores),
                    "--sources-csv",
                    str(sources),
                    "--output-dir",
                    str(root / "output"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unavailable evidence sources must have zero counts", result.stderr)

    def test_preparer_rejects_more_than_twenty_evidence_items(self) -> None:
        module = _load_preparer_module()
        with tempfile.TemporaryDirectory() as temporary:
            sources = Path(temporary) / "sources.csv"
            _write_csv(
                sources,
                [
                    "source_name",
                    "source_kind",
                    "item_count",
                    "visible_text_unit_count",
                    "status",
                ],
                [
                    ["Codex", "conversation_history", "20", "160", "available"],
                    ["Selected request", "explicit_user_content", "1", "8", "available"],
                ],
            )

            with self.assertRaisesRegex(
                ValueError,
                "total inspected evidence items must be between 1 and 20",
            ):
                module.parse_sources(sources)

    def test_preparer_accepts_client_neutral_explicit_user_content(self) -> None:
        module = _load_preparer_module()
        with tempfile.TemporaryDirectory() as temporary:
            sources = Path(temporary) / "sources.csv"
            _write_csv(
                sources,
                [
                    "source_name",
                    "source_kind",
                    "item_count",
                    "visible_text_unit_count",
                    "status",
                ],
                [
                    ["Codex", "conversation_history", "7", "42", "available"],
                    ["Selected request", "explicit_user_content", "1", "1", "available"],
                ],
            )

            parsed = module.parse_sources(sources)

            self.assertEqual(parsed[0]["source_name"], "Codex")
            self.assertEqual(parsed[1]["source_kind"], "explicit_user_content")
            self.assertNotIn("codex_task_count", parsed[0])

    def test_preparer_rejects_legacy_and_duplicate_source_audits(self) -> None:
        module = _load_preparer_module()
        with tempfile.TemporaryDirectory() as temporary:
            sources = Path(temporary) / "sources.csv"
            _write_csv(
                sources,
                ["source_type", "conversation_count", "turn_count", "status"],
                [["codex", "1", "2", "available"]],
            )
            with self.assertRaisesRegex(ValueError, "columns must be"):
                module.parse_sources(sources)

            _write_csv(
                sources,
                [
                    "source_name",
                    "source_kind",
                    "item_count",
                    "visible_text_unit_count",
                    "status",
                ],
                [
                    ["Codex", "conversation_history", "1", "2", "available"],
                    [" codex ", "explicit_user_content", "1", "1", "available"],
                ],
            )
            with self.assertRaisesRegex(ValueError, "evidence source names must be distinct"):
                module.parse_sources(sources)

    def test_preparer_accepts_the_exact_sixteen_archetype_names(self) -> None:
        module = _load_preparer_module()
        for archetype in WORK_ARCHETYPES:
            self.assertEqual(module._canonical_archetype(archetype), archetype)
            self.assertEqual(module._canonical_archetype(archetype.upper()), archetype)

    def test_preparer_requires_five_distinct_single_lexical_unit_keywords(self) -> None:
        module = _load_preparer_module()
        with self.assertRaisesRegex(ValueError, "exactly five keywords"):
            module._parse_keyword_prose(
                ["Calm, Candid, Steady, Curious", "Supporting prose."],
                "People that help me thrive",
            )
        with self.assertRaisesRegex(ValueError, "single lexical units"):
            module._parse_keyword_prose(
                ["Calm, Open minded, Steady, Curious, Direct", "Supporting prose."],
                "People that help me thrive",
            )
        self.assertEqual(
            module._parse_keywords("坦诚，稳健，敏锐，独立，可靠", "People that help me thrive"),
            ["坦诚", "稳健", "敏锐", "独立", "可靠"],
        )
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            module._parse_keyword_prose(
                ["Calm, Candid, calm, Curious, Direct", "Supporting prose."],
                "People that help me thrive",
            )

    def test_preparer_rejects_chinese_tag_when_generated_content_is_not_chinese(self) -> None:
        module = _load_preparer_module()
        chinese_tagged = MANUAL.replace("Output Language: en", "Output Language: zh-CN")

        with self.assertRaisesRegex(ValueError, "does not predominantly match"):
            module.parse_manual(chinese_tagged)
        module._validate_manual_language(
            {"prose": "我会先理解问题，再根据证据做出清晰判断，并记录下一步行动。"},
            "zh-CN",
        )

        with self.assertRaisesRegex(ValueError, "exactly en or zh-CN"):
            module.parse_manual(MANUAL.replace("Output Language: en", "Output Language: ja"))

    def test_preparer_rejects_unknown_or_mismatched_archetypes(self) -> None:
        module = _load_preparer_module()
        with self.assertRaisesRegex(ValueError, "unsupported Work Archetype"):
            module._canonical_archetype("The Placeholder")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manual = root / "manual.md"
            scores = root / "scores.csv"
            sources = root / "sources.csv"
            manual.write_text(MANUAL, encoding="utf-8")
            _write_csv(
                scores,
                ["category", "key", "value", "confidence"],
                [
                    ["archetype", "work_archetype", "The Guide", ""],
                    *[["dimension", f"dimension_{index}", "50", "0.5"] for index in range(1, 5)],
                    ["overall", "archetype_confidence", "50", ""],
                    ["facet", "Ideas", "50", "0.5"],
                ],
            )
            _write_csv(
                sources,
                [
                    "source_name",
                    "source_kind",
                    "item_count",
                    "visible_text_unit_count",
                    "status",
                ],
                [["Codex", "conversation_history", "1", "2", "available"]],
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PREPARER),
                    "--manual-md",
                    str(manual),
                    "--scores-csv",
                    str(scores),
                    "--sources-csv",
                    str(sources),
                    "--output-dir",
                    str(root / "output"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Work Archetype values must match", result.stderr)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _read_raw(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _load_preparer_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("personal_manual_preparer", PREPARER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Personal Manual preparer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
