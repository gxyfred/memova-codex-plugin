#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "personal_manual_v1"
MARKDOWN_NAME = "personal-manual.md"
SCORES_NAME = "personal-manual-scores.csv"
SOURCES_NAME = "personal-manual-sources.csv"
UPLOAD_NAME = "personal-manual-upload.json"
MAX_MARKDOWN_BYTES = 300_000
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
    if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise ValueError(f"manual Markdown exceeds {MAX_MARKDOWN_BYTES} UTF-8 bytes")
    document = parse_manual(markdown)
    score_data = parse_scores(scores_path)
    source_statistics = parse_sources(sources_path)
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
            "source_statistics": source_statistics,
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
    print(
        json.dumps(
            {
                "markdown_path": str(markdown_output),
                "scores_csv_path": str(scores_output),
                "sources_csv_path": str(sources_output),
                "upload_json_path": str(upload_output),
                "work_archetype": score_data["work_archetype"],
                "source_statistics": source_statistics,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def parse_manual(markdown: str) -> dict[str, Any]:
    lines = markdown.splitlines()
    archetype_from_text = _extract_archetype(lines)
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
    return {"work_archetype": archetype_from_text, "manual": manual}


def parse_scores(path: Path) -> dict[str, Any]:
    rows = _csv_rows(path, {"category", "key", "value", "confidence"})
    keyed: dict[tuple[str, str], str] = {}
    for row in rows:
        identity = (row["category"].strip().casefold(), row["key"].strip())
        if identity in keyed:
            raise ValueError(f"duplicate score row: {identity}")
        keyed[identity] = row["value"].strip()
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


def parse_sources(path: Path) -> dict[str, Any]:
    rows = _csv_rows(path, {"source_type", "conversation_count", "turn_count", "status"})
    by_source = {row["source_type"].strip().casefold(): row for row in rows}
    if set(by_source) != {"codex", "chatgpt"}:
        raise ValueError("sources CSV must contain exactly one codex and one chatgpt row")
    codex = by_source["codex"]
    chatgpt = by_source["chatgpt"]
    codex_count = _count(codex["conversation_count"], "codex conversation_count", maximum=50)
    codex_turns = _count(codex["turn_count"], "codex turn_count", maximum=50_000)
    chatgpt_count = _count(chatgpt["conversation_count"], "chatgpt conversation_count", maximum=50)
    chatgpt_turns = _count(chatgpt["turn_count"], "chatgpt turn_count", maximum=50_000)
    status = chatgpt["status"].strip().casefold()
    if status not in {"available", "unavailable"}:
        raise ValueError("chatgpt status must be available or unavailable")
    if not 1 <= codex_count + chatgpt_count <= 50:
        raise ValueError("total inspected conversations must be between 1 and 50")
    if (codex_count == 0) != (codex_turns == 0):
        raise ValueError("Codex conversation and turn counts are inconsistent")
    if (chatgpt_count == 0) != (chatgpt_turns == 0):
        raise ValueError("ChatGPT conversation and turn counts are inconsistent")
    if status == "unavailable" and (chatgpt_count or chatgpt_turns):
        raise ValueError("unavailable ChatGPT history must have zero counts")
    return {
        "codex_task_count": codex_count,
        "codex_turn_count": codex_turns,
        "chatgpt_chat_count": chatgpt_count,
        "chatgpt_turn_count": chatgpt_turns,
        "chatgpt_status": status,
    }


def _extract_archetype(lines: list[str]) -> str:
    matches = []
    for line in lines:
        match = re.fullmatch(r"\s*(?:#+\s*)?Work Archetype:\s*(.+?)\s*", line, re.I)
        if match:
            matches.append(match.group(1))
    if len(matches) != 1:
        raise ValueError("manual must contain exactly one Work Archetype line")
    return _canonical_archetype(matches[0])


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
    parts = [item.strip() for item in re.split(r"[,·]", value) if item.strip()]
    if len(parts) != 5:
        raise ValueError(f"{marker} must contain exactly five keywords")
    if not all(re.fullmatch(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", item) for item in parts):
        raise ValueError(f"{marker} keywords must be single English words")
    if len({item.casefold() for item in parts}) != 5:
        raise ValueError(f"{marker} keywords must be distinct")
    return parts


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


def _csv_rows(path: Path, fields: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or ()) != fields:
            raise ValueError(f"{path.name} columns must be {sorted(fields)}")
        rows = list(reader)
    if not rows:
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


def _copy_if_different(source: Path, target: Path) -> None:
    if source != target:
        shutil.copyfile(source, target)


if __name__ == "__main__":
    raise SystemExit(main())
