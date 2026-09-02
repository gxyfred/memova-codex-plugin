#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "personal_manual_v1"
GENERATION_CONTRACT_VERSION = "personal_manual_generation_v5"
AUDIT_FORMAT_VERSION = "personal_manual_audit_csv_v2"
MARKDOWN_NAME = "personal-manual.md"
SCORES_NAME = "personal-manual-scores.csv"
SOURCES_NAME = "personal-manual-sources.csv"
UPLOAD_NAME = "personal-manual-upload.json"
MAX_MARKDOWN_BYTES = 300_000
MAX_SCORES_CSV_BYTES = 64 * 1024
MAX_SOURCES_CSV_BYTES = 16 * 1024
DISCLAIMER = (
    "These results describe patterns visible in your available AI conversations. They may change "
    "across roles, tasks, and periods of life, and you can correct any interpretation that does "
    "not fit."
)
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
AUDIT_FACET_NAMES = frozenset(
    {
        "aesthetics",
        "adventurousness",
        "ambiguity acceptance",
        "assertiveness",
        "breadth",
        "deliberation",
        "divergent exploration",
        "excitement-seeking",
        "feelings",
        "friendliness",
        "gregariousness",
        "ideas",
        "imagination",
        "modesty",
        "order",
        "positive emotionality",
        "self-discipline",
    }
)

FIELD_MARKERS = (
    ("how_i_think", "How I think", "prose"),
    ("how_i_read", "How I read", "prose"),
    ("how_i_write", "How I write", "prose"),
    ("what_gives_me_energy", "What gives me energy", "list"),
    ("what_i_care_about", "What I care about", "list"),
    ("how_i_communicate", "How I communicate", "prose"),
    ("how_to_work_with_me", "How to work with me", "list"),
    ("people_that_help_me_thrive", "People that help me thrive", "keyword_prose"),
    (
        "environments_that_help_me_thrive",
        "Environments that help me thrive",
        "keyword_prose",
    ),
    ("my_strengths", "My strengths", "prose"),
    ("current_growth_edge", "Current growth edge", "prose"),
    ("internal_conflicts", "Internal conflicts", "list"),
    ("person_i_am_trying_to_become", "The person I am trying to become", "prose"),
    ("advice_from_memova", "Advice from Memova", "list"),
)
KEYWORD_OUTPUT_FIELDS = {
    "people_that_help_me_thrive": "people_keywords",
    "environments_that_help_me_thrive": "environment_keywords",
}
SECTION_HEADINGS = {
    "1. how i operate",
    "2. what moves and grounds me",
    "3. relationships and collaboration",
    "4. what makes me distinctive",
    "5. moving forward",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Personal Manual artifacts and build the private MCP upload payload."
    )
    parser.add_argument("--manual-md", required=True)
    parser.add_argument("--scores-csv", required=True)
    parser.add_argument("--sources-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-note-version-id")
    args = parser.parse_args()

    manual_path = Path(args.manual_md).expanduser().resolve()
    scores_path = Path(args.scores_csv).expanduser().resolve()
    sources_path = Path(args.sources_csv).expanduser().resolve()
    markdown = manual_path.read_text(encoding="utf-8")
    scores_csv = _read_utf8_verbatim(
        scores_path, maximum=MAX_SCORES_CSV_BYTES
    )
    sources_csv = _read_utf8_verbatim(
        sources_path, maximum=MAX_SOURCES_CSV_BYTES
    )
    if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise ValueError(f"manual Markdown exceeds {MAX_MARKDOWN_BYTES} UTF-8 bytes")
    document = parse_manual(markdown)
    score_data = parse_scores(scores_path)
    evidence_sources = parse_sources(sources_path)
    if document["work_archetype"] != score_data["work_archetype"]:
        raise ValueError("Markdown and scores CSV Work Archetype values must match")
    document["work_archetype"] = score_data["work_archetype"]
    document["dimension_scores"] = score_data["dimension_scores"]

    expected_version = args.expected_note_version_id or None
    if expected_version is not None:
        expected_version = str(uuid.UUID(expected_version))
    normalized_markdown = markdown.rstrip() + "\n"
    stable = {
        "schema_version": SCHEMA_VERSION,
        "markdown_content": normalized_markdown,
        "document": document,
        "private_metadata": {
            "archetype_confidence": score_data["archetype_confidence"],
            "generation_contract_version": GENERATION_CONTRACT_VERSION,
            "evidence_sources": evidence_sources,
            "personal_manual_audit": {
                "format_version": AUDIT_FORMAT_VERSION,
                "scores_csv": scores_csv,
                "sources_csv": sources_csv,
            },
        },
    }
    canonical = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "idempotency_key": f"personal-manual-{hashlib.sha256(canonical.encode()).hexdigest()}",
        "expected_note_version_id": expected_version,
        "markdown_content": normalized_markdown,
        "document": document,
        "private_metadata": stable["private_metadata"],
    }

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_dir.chmod(0o700)
    except OSError:
        pass
    markdown_output = output_dir / MARKDOWN_NAME
    scores_output = output_dir / SCORES_NAME
    sources_output = output_dir / SOURCES_NAME
    upload_output = output_dir / UPLOAD_NAME
    markdown_output.write_text(normalized_markdown, encoding="utf-8", newline="\n")
    _copy_if_different(scores_path, scores_output)
    _copy_if_different(sources_path, sources_output)
    upload_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for path in (markdown_output, scores_output, sources_output, upload_output):
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return 0


def parse_manual(markdown: str) -> dict[str, Any]:
    lines = markdown.splitlines()
    archetype_from_text = _extract_archetype(lines)
    language_code = _extract_language_code(lines)
    positions: list[int] = []
    normalized = [_heading_text(line) for line in lines]
    for _, marker, _ in FIELD_MARKERS:
        candidates = [index for index, value in enumerate(normalized) if value == marker.casefold()]
        if len(candidates) != 1:
            raise ValueError(f"manual must contain exactly one '{marker}' heading")
        positions.append(candidates[0])
    if positions != sorted(positions):
        raise ValueError("manual headings are not in the required order")

    manual: dict[str, Any] = {}
    for index, (key, marker, kind) in enumerate(FIELD_MARKERS):
        start = positions[index] + 1
        end = positions[index + 1] if index + 1 < len(positions) else len(lines)
        content_lines = _content_lines(lines[start:end])
        if key == "advice_from_memova":
            content_lines = _stop_before_disclaimer(content_lines)
        if kind == "list":
            value: Any = _parse_list(content_lines, marker)
        elif kind == "keyword_prose":
            keywords, value = _parse_keyword_prose(content_lines, marker)
            manual[KEYWORD_OUTPUT_FIELDS[key]] = keywords
        else:
            value = _parse_prose(content_lines, marker)
        manual[key] = value
    if len(manual["what_gives_me_energy"]) > 3 or len(manual["what_i_care_about"]) > 3:
        raise ValueError("energy and care sections support at most three items")
    if len(manual["how_to_work_with_me"]) > 3 or len(manual["internal_conflicts"]) > 3:
        raise ValueError("collaboration and conflict sections support at most three items")
    if not 2 <= len(manual["advice_from_memova"]) <= 3:
        raise ValueError("Advice from Memova must contain two or three items")
    _validate_manual_language(manual, language_code)
    return {
        "work_archetype": archetype_from_text,
        "language_code": language_code,
        "manual": manual,
    }


def parse_scores(path: Path) -> dict[str, Any]:
    rows = _csv_rows(path, ("category", "key", "value", "confidence"))
    if not 7 <= len(rows) <= 24:
        raise ValueError("scores CSV must contain between 7 and 24 rows")
    keyed: dict[tuple[str, str], str] = {}
    facet_count = 0
    for row in rows:
        identity = (row["category"].strip().casefold(), row["key"].strip())
        if identity in keyed:
            raise ValueError(f"duplicate score row: {identity}")
        keyed[identity] = row["value"].strip()
        category, key = identity
        if category == "facet":
            if key.casefold() not in AUDIT_FACET_NAMES:
                raise ValueError(f"unsupported facet: {key}")
            _score(row["value"].strip(), key)
            _confidence(row["confidence"], f"{key} confidence")
            facet_count += 1
        elif category == "dimension" and key in {
            "dimension_1", "dimension_2", "dimension_3", "dimension_4"
        }:
            _confidence(row["confidence"], f"{key} confidence")
        elif identity in {
            ("archetype", "work_archetype"),
            ("overall", "archetype_confidence"),
        }:
            if row["confidence"].strip():
                raise ValueError(f"{key} confidence column must be empty")
        else:
            raise ValueError(f"unsupported score row: {identity}")
    if facet_count == 0:
        raise ValueError("scores CSV must contain at least one supported facet row")
    raw_archetype = keyed.get(("archetype", "work_archetype"), "")
    if not raw_archetype:
        raise ValueError("scores CSV is missing archetype/work_archetype")
    archetype = _canonical_archetype(raw_archetype)
    dimensions = {
        key: _score(keyed.get(("dimension", key)), key)
        for key in ("dimension_1", "dimension_2", "dimension_3", "dimension_4")
    }
    overall = _score(
        keyed.get(("overall", "archetype_confidence")), "archetype_confidence", minimum=1
    )
    return {
        "work_archetype": archetype,
        "dimension_scores": dimensions,
        "archetype_confidence": overall,
    }


def parse_sources(path: Path) -> list[dict[str, Any]]:
    rows = _csv_rows(
        path,
        (
            "source_name",
            "source_kind",
            "item_count",
            "visible_text_unit_count",
            "status",
        ),
    )
    if len(rows) > 8:
        raise ValueError("sources CSV must contain at most eight evidence-source rows")

    evidence_sources: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    inspected_items = 0
    for row in rows:
        source_name = row["source_name"].strip()
        if (
            not source_name
            or len(source_name) > 64
            or any(ord(character) < 32 for character in source_name)
        ):
            raise ValueError("source_name must be 1-64 characters of visible text")
        normalized_name = source_name.casefold()
        if normalized_name in seen_names:
            raise ValueError("evidence source names must be distinct")
        seen_names.add(normalized_name)

        source_kind = row["source_kind"].strip().casefold()
        if source_kind not in {"conversation_history", "explicit_user_content"}:
            raise ValueError(
                "source_kind must be conversation_history or explicit_user_content"
            )
        item_count = _count(row["item_count"], f"{source_name} item_count", maximum=50)
        visible_text_unit_count = _count(
            row["visible_text_unit_count"],
            f"{source_name} visible_text_unit_count",
            maximum=50_000,
        )
        status = row["status"].strip().casefold()
        if status not in {"available", "unavailable"}:
            raise ValueError("evidence source status must be available or unavailable")
        if status == "unavailable" and (item_count or visible_text_unit_count):
            raise ValueError("unavailable evidence sources must have zero counts")
        if item_count == 0 and visible_text_unit_count != 0:
            raise ValueError("visible_text_unit_count must be zero when item_count is zero")
        if item_count > 0 and visible_text_unit_count == 0:
            raise ValueError("visible_text_unit_count must be positive when items were inspected")
        if status == "available":
            inspected_items += item_count
        evidence_sources.append(
            {
                "source_name": source_name,
                "source_kind": source_kind,
                "item_count": item_count,
                "visible_text_unit_count": visible_text_unit_count,
                "status": status,
            }
        )

    if not 1 <= inspected_items <= 20:
        raise ValueError("total inspected evidence items must be between 1 and 20")
    return evidence_sources


def _extract_archetype(lines: list[str]) -> str:
    matches = []
    for line in lines:
        match = re.fullmatch(r"\s*(?:#+\s*)?Work Archetype:\s*(.+?)\s*", line, re.I)
        if match:
            matches.append(match.group(1))
    if len(matches) != 1:
        raise ValueError("manual must contain exactly one Work Archetype line")
    return _canonical_archetype(matches[0])


def _extract_language_code(lines: list[str]) -> str:
    matches = []
    for line in lines:
        match = re.fullmatch(r"\s*(?:#+\s*)?Output Language:\s*(.+?)\s*", line, re.I)
        if match:
            matches.append(match.group(1).strip())
    if len(matches) != 1:
        raise ValueError("manual must contain exactly one Output Language line")
    language_code = matches[0]
    if language_code not in {"en", "zh-CN"}:
        raise ValueError("Output Language must be exactly en or zh-CN")
    return language_code


def _canonical_archetype(value: str) -> str:
    normalized = value.strip().casefold()
    for archetype in WORK_ARCHETYPES:
        if normalized == archetype.casefold():
            return archetype
    raise ValueError(f"unsupported Work Archetype: {value}")


def _heading_text(line: str) -> str:
    value = re.sub(r"^\s*#+\s*", "", line).strip()
    return value.casefold()


def _content_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if _heading_text(line) not in SECTION_HEADINGS]


def _stop_before_disclaimer(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        if line.strip().startswith("These results describe patterns visible"):
            if line.strip() != DISCLAIMER:
                raise ValueError("Personal Manual disclaimer does not match the required text")
            return lines[:index]
    raise ValueError("Personal Manual is missing the required final disclaimer")


def _parse_prose(lines: list[str], marker: str) -> str:
    value = " ".join(line.strip() for line in lines if line.strip()).strip()
    if not value:
        raise ValueError(f"{marker} must contain prose")
    return value


def _parse_keyword_prose(lines: list[str], marker: str) -> tuple[list[str], str]:
    values = [line.strip() for line in lines if line.strip()]
    if not values:
        raise ValueError(f"{marker} must contain a keyword line and prose")
    keywords = _parse_keywords(values[0], marker)
    return keywords, _parse_prose(values[1:], marker)


def _parse_keywords(value: str, marker: str) -> list[str]:
    parts = [item.strip() for item in re.split(r"[,，、·]", value) if item.strip()]
    if len(parts) != 5:
        raise ValueError(f"{marker} must contain exactly five keywords")
    if not all(
        re.fullmatch(r"[^\s,，、·;；]+", item)
        and any(character.isalnum() for character in item)
        and len(item) <= 64
        for item in parts
    ):
        raise ValueError(f"{marker} keywords must be single lexical units")
    if len({item.casefold() for item in parts}) != 5:
        raise ValueError(f"{marker} keywords must be distinct")
    return parts


def _validate_manual_language(manual: dict[str, Any], language_code: str) -> None:
    if language_code != "zh-CN":
        return
    values: list[str] = []
    for value in manual.values():
        values.extend(value if isinstance(value, list) else [value])
    combined = "".join(values)
    cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", combined))
    latin_count = len(re.findall(r"[A-Za-z]", combined))
    if cjk_count < 8 or cjk_count <= latin_count:
        raise ValueError(
            "generated Personal Manual content does not predominantly match Output Language zh"
        )


def _parse_list(lines: list[str], marker: str) -> list[str]:
    values = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^(?:[-*•]|\d+[.)])\s+(.+)$", stripped)
        if not match:
            raise ValueError(f"{marker} must contain only Markdown list items")
        values.append(match.group(1).strip())
    if not values:
        raise ValueError(f"{marker} must contain at least one item")
    return values


def _csv_rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError(f"{path.name} columns must be {list(fields)}")
        rows = list(reader)
    if not rows or any(
        None in row or any(item is None for item in row.values()) for row in rows
    ):
        raise ValueError(f"{path.name} must contain data rows")
    return rows


def _score(value: str | None, field: str, *, minimum: int = 0) -> int:
    if value is None or not value.isdigit():
        raise ValueError(f"{field} must be an integer score")
    score = int(value)
    if not minimum <= score <= 100:
        raise ValueError(f"{field} must be between {minimum} and 100")
    return score


def _count(value: str, field: str, *, maximum: int) -> int:
    if not value.strip().isdigit():
        raise ValueError(f"{field} must be a non-negative integer")
    count = int(value)
    if count > maximum:
        raise ValueError(f"{field} must not exceed {maximum}")
    return count


def _confidence(value: str, field: str) -> float:
    try:
        confidence = float(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError(f"{field} must be between 0 and 1")
    return confidence


def _copy_if_different(source: Path, target: Path) -> None:
    if source != target:
        shutil.copyfile(source, target)


def _read_utf8_verbatim(path: Path, *, maximum: int) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        value = handle.read()
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{path.name} exceeds {maximum} UTF-8 bytes")
    if "\x00" in value:
        raise ValueError(f"{path.name} must not contain NUL bytes")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
