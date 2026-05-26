from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEMPLATE_VERSION = "memova_inbox_v1"
SETUP_SCHEMA_VERSION = "knowledge_base_setup_v1"
INPUT_ROOT_RELATIVE_PATH = "inbox/memova"
INPUT_ROOT_FOLDER_NAME = "Memova"
ALLOWED_SETUP_MODES = {"create_new_vault", "connect_existing_vault"}

NEW_VAULT_DIRS = [
    "inbox/memova/schemas",
    "inbox/memova/meetings",
    "inbox/memova/imports",
    "inbox/memova/attachments",
    "inbox/memova/_memova",
    "sources",
    "wiki",
    "projects",
    "daily",
    "outputs",
    "archive",
    "schemas",
    "_memova",
]

INPUT_ROOT_DIRS = [
    "schemas",
    "meetings",
    "imports",
    "attachments",
    "_memova",
]

NEW_VAULT_REQUIRED_ROOTS = [
    "README.md",
    "AGENTS.md",
    "inbox/",
    "inbox/README.md",
    "inbox/memova/",
    "sources/",
    "sources/README.md",
    "wiki/",
    "wiki/README.md",
    "projects/",
    "projects/README.md",
    "daily/",
    "daily/README.md",
    "outputs/",
    "outputs/README.md",
    "archive/",
    "archive/README.md",
    "schemas/",
    "schemas/README.md",
    "_memova/",
]

INPUT_ROOT_REQUIRED_FILES = [
    "README.md",
    "AGENTS.md",
    "schemas/meeting_packet.schema.md",
    "schemas/transcript.schema.md",
    "schemas/note.schema.md",
    "schemas/ocr.schema.md",
    "schemas/attachment.schema.md",
    "_memova/manifest.json",
    "_memova/input_root.json",
    "_memova/sync_state.json",
    "_memova/source_index.json",
]

NEW_VAULT_DOC_CHECKS = {
    "README.md": ["Memova Vault", "inbox/memova", "V1 Scope"],
    "AGENTS.md": ["No memory without source", "No external write without confirmation"],
    "inbox/README.md": ["Inbox", "inbox/memova"],
    "sources/README.md": ["Sources", "Memova V1"],
    "wiki/README.md": ["Wiki", "curated long-term knowledge"],
    "projects/README.md": ["Projects", "project-specific"],
    "daily/README.md": ["Daily", "daily notes"],
    "outputs/README.md": ["Outputs", "finished artifacts"],
    "archive/README.md": ["Archive", "inactive material"],
    "schemas/README.md": ["Schemas", "inbox/memova/schemas"],
}

INPUT_ROOT_DOC_CHECKS = {
    "README.md": [
        "Memova Raw Input Root",
        "meetings/YYYY/MM",
        "manifest.json",
        "media/audio_manifest.json",
    ],
    "AGENTS.md": [
        "Agent Rules",
        "No memory without source",
        "No action without evidence",
        "Reading Order",
    ],
    "schemas/meeting_packet.schema.md": [
        "Meeting Packet Schema",
        "transcript.md",
        "final_note.json",
        "hashes.json",
    ],
    "schemas/transcript.schema.md": [
        "Transcript Schema",
        "transcript.md",
        "transcript.json",
        "stable post-meeting transcript",
    ],
    "schemas/note.schema.md": [
        "Note Schema",
        "raw_user_note",
        "final_note",
        "Grounding Rules",
    ],
    "schemas/ocr.schema.md": [
        "OCR Schema",
        "ocr/imports.json",
        "pages.json",
        "files/page-001.png",
    ],
    "schemas/attachment.schema.md": [
        "Attachment And Image Schema",
        "attachments.json",
        "images.json",
        "analysis_images",
    ],
}

RAW_INPUT_PARENT_SCORES = {
    "00_inbox": 100,
    "inbox": 95,
    "sources": 90,
    "source": 88,
    "resources": 85,
    "resource": 83,
    "captures": 80,
    "capture": 78,
    "fleeting notes": 75,
    "imports": 70,
    "import": 68,
}


@dataclass(frozen=True)
class FileSpec:
    path: str
    content: str
    machine: bool = False


def markdown(text: str) -> str:
    return text.strip() + "\n"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_setup_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if "setup_package" in data and isinstance(data["setup_package"], dict):
        return data["setup_package"]
    return data


def write_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def expand_path(path: str) -> Path:
    return Path(path).expanduser()


def resolved(path: Path) -> Path:
    return path.resolve(strict=False)


def is_relative_safe(relative_path: str) -> bool:
    candidate = Path(relative_path)
    return not candidate.is_absolute() and ".." not in candidate.parts


def safe_join(root: Path, relative_path: str) -> Path:
    if not is_relative_safe(relative_path):
        raise ValueError(f"Unsafe relative path: {relative_path}")
    target = resolved(root / relative_path)
    root_resolved = resolved(root)
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"Path escapes target root: {relative_path}")
    return target


def detect_icloud_roots() -> list[dict[str, str]]:
    home = Path.home()
    candidates = [
        home / "Library" / "Mobile Documents" / "com~apple~CloudDocs",
        home / "iCloud Drive",
    ]
    mobile_documents = home / "Library" / "Mobile Documents"
    if mobile_documents.exists():
        for child in mobile_documents.iterdir():
            if child.is_dir() and "CloudDocs" in child.name and child not in candidates:
                candidates.append(child)

    results = []
    seen: set[str] = set()
    for path in candidates:
        expanded = resolved(path)
        key = str(expanded)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "path": key,
                "exists": path.exists(),
                "recommended_new_vault": str(expanded / "Memova Vault"),
            },
        )
    return results


def path_under_icloud(path: Path) -> bool:
    target = resolved(path)
    for candidate in detect_icloud_roots():
        root = Path(candidate["path"])
        if target == root or root in target.parents:
            return True
    return False


def relative_to_icloud(path: Path) -> str | None:
    target = resolved(path)
    for candidate in detect_icloud_roots():
        if not candidate.get("exists"):
            continue
        root = Path(candidate["path"])
        if target == root:
            return ""
        if root in target.parents:
            return target.relative_to(root).as_posix()
    return None


def join_relative(*parts: str | None) -> str | None:
    cleaned = [str(part).replace("\\", "/").strip("/") for part in parts if str(part or "").strip("/")]
    if not cleaned:
        return None
    return str(Path(cleaned[0], *cleaned[1:])).replace("\\", "/")


def safe_component(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[/:\\]+", "-", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^A-Za-z0-9 ._()&+-]", "", value)
    return value[:80].strip(" ._-") or "Untitled"


def setup_mode(setup: dict[str, Any]) -> str:
    return str(setup.get("setup_mode") or "create_new_vault")


def is_existing_vault_setup(setup: dict[str, Any]) -> bool:
    return setup_mode(setup) == "connect_existing_vault"


def manifest_id(setup: dict[str, Any]) -> str:
    setup_id = setup.get("setup_session_id")
    if isinstance(setup_id, str) and setup_id:
        return f"memova-vault-{setup_id}"
    return "memova-vault-local"


def input_root_manifest_id(setup: dict[str, Any]) -> str:
    setup_id = setup.get("setup_session_id")
    if isinstance(setup_id, str) and setup_id:
        return f"memova-input-root-{setup_id}"
    return "memova-input-root-local"


def detect_language() -> str:
    locale = " ".join(
        value
        for value in (
            os.environ.get("LC_ALL"),
            os.environ.get("LC_MESSAGES"),
            os.environ.get("LANG"),
        )
        if value
    ).lower()
    if locale.startswith("zh") or ".zh" in locale or "_zh" in locale:
        return "zh"
    return "en"


def input_root_folder_name(setup: dict[str, Any]) -> str:
    hints = setup.get("target_path_hints") or {}
    if isinstance(hints, dict):
        for key in (
            "desired_input_folder_name",
            "memova_folder_name",
            "desired_memova_folder_name",
        ):
            value = hints.get(key)
            if isinstance(value, str) and value.strip():
                return safe_component(value)
    return INPUT_ROOT_FOLDER_NAME


def extract_source_vault_paths(setup: dict[str, Any]) -> list[Path]:
    hints = setup.get("source_path_hints") or {}
    raw_paths: list[str] = []
    path_keys = {
        "mac_existing_vault_path",
        "mac_path",
        "existing_vault_path",
        "old_vault_path",
        "source_path",
        "vault_path",
        "path",
    }
    list_keys = {"candidate_paths", "existing_vault_paths", "paths"}

    def visit(value: Any, *, key: str | None = None) -> None:
        if isinstance(value, str) and key in path_keys:
            raw_paths.append(value)
        elif isinstance(value, list) and key in list_keys:
            raw_paths.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, key=child_key)

    visit(hints)

    paths: list[Path] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        expanded = resolved(expand_path(raw_path))
        key = str(expanded)
        if key not in seen:
            seen.add(key)
            paths.append(expanded)
    return paths


def path_inside(parent: Path, child: Path) -> bool:
    parent_resolved = resolved(parent)
    child_resolved = resolved(child)
    return child_resolved == parent_resolved or parent_resolved in child_resolved.parents


def raw_input_candidates(root: Path, *, max_depth: int = 2, max_entries: int = 300) -> list[dict[str, Any]]:
    root = expand_path(str(root))
    candidates: list[dict[str, Any]] = []
    if not root.exists():
        return candidates
    seen = 0
    for current_root, dirnames, _filenames in os.walk(root):
        current = Path(current_root)
        relative = current.relative_to(root)
        depth = 0 if str(relative) == "." else len(relative.parts)
        if depth >= max_depth:
            dirnames[:] = []
        for dirname in sorted(dirnames):
            seen += 1
            if seen > max_entries:
                return sorted(candidates, key=lambda item: item["score"], reverse=True)
            normalized = dirname.strip().lower().replace("-", "_").replace(" ", "_")
            spaced = normalized.replace("_", " ")
            score = RAW_INPUT_PARENT_SCORES.get(normalized) or RAW_INPUT_PARENT_SCORES.get(spaced)
            if score:
                rel = str((relative / dirname) if str(relative) != "." else Path(dirname))
                candidates.append(
                    {
                        "path": str(resolved(root / rel)),
                        "relative_path": rel,
                        "score": score - depth,
                        "reason": f"Directory name looks like a raw-input area: {dirname}",
                    },
                )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def suggested_existing_input_target(setup: dict[str, Any], existing_vault_path: Path) -> Path:
    candidates = raw_input_candidates(existing_vault_path)
    folder_name = input_root_folder_name(setup)
    if candidates:
        return resolved(Path(candidates[0]["path"]) / folder_name)
    return resolved(existing_vault_path / folder_name)


def memova_input_root_relative_path(setup: dict[str, Any], target_root: Path) -> str:
    if not is_existing_vault_setup(setup):
        return INPUT_ROOT_RELATIVE_PATH
    target = resolved(target_root)
    for source in extract_source_vault_paths(setup):
        source_resolved = resolved(source)
        if target == source_resolved:
            return "."
        if source_resolved in target.parents:
            return str(target.relative_to(source_resolved))
    return "."


def root_manifest(setup: dict[str, Any], *, now: str) -> dict[str, Any]:
    return {
        "schema_version": "memova_vault_manifest_v1",
        "manifest_id": manifest_id(setup),
        "created_at": now,
        "updated_at": now,
        "setup_session_id": setup.get("setup_session_id"),
        "workspace_id": setup.get("workspace_id"),
        "vault_template_version": setup.get("vault_template_version") or TEMPLATE_VERSION,
        "setup_package_schema_version": setup.get("schema_version") or SETUP_SCHEMA_VERSION,
        "setup_mode": setup_mode(setup),
        "storage_target": setup.get("storage_target") or "icloud_drive",
        "memova_input_root_relative_path": INPUT_ROOT_RELATIVE_PATH,
        "ownership_scope": "raw_input_layer_only",
    }


def input_root_manifest(
    setup: dict[str, Any],
    *,
    now: str,
    relative_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": "memova_input_root_manifest_v1",
        "manifest_id": input_root_manifest_id(setup),
        "vault_manifest_id": manifest_id(setup),
        "created_at": now,
        "updated_at": now,
        "setup_session_id": setup.get("setup_session_id"),
        "workspace_id": setup.get("workspace_id"),
        "vault_template_version": setup.get("vault_template_version") or TEMPLATE_VERSION,
        "setup_package_schema_version": setup.get("schema_version") or SETUP_SCHEMA_VERSION,
        "setup_mode": setup_mode(setup),
        "storage_target": setup.get("storage_target") or "icloud_drive",
        "memova_input_root_relative_path": relative_path,
        "ownership_scope": "raw_input_layer_only",
        "audio_files_written_by_default": False,
    }


def input_root_file_specs(
    setup: dict[str, Any],
    *,
    now: str,
    relative_path: str,
    prefix: str = "",
) -> list[FileSpec]:
    files = [
        FileSpec("README.md", input_root_readme(relative_path=relative_path), machine=True),
        FileSpec("AGENTS.md", input_root_agents(relative_path=relative_path), machine=True),
        FileSpec(
            "_memova/manifest.json",
            json.dumps(input_root_manifest(setup, now=now, relative_path=relative_path), indent=2, ensure_ascii=False)
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/input_root.json",
            json.dumps(
                {
                    "schema_version": "memova_input_root_v1",
                    "updated_at": now,
                    "relative_path": relative_path,
                    "meeting_packet_root": "meetings",
                    "imports_root": "imports",
                    "attachments_root": "attachments",
                    "writes_audio_files_by_default": False,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/sync_state.json",
            json.dumps(
                {
                    "schema_version": "memova_input_sync_state_v1",
                    "updated_at": now,
                    "last_successful_sync_at": None,
                    "meeting_packets": {},
                    "conflicts": [],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/source_index.json",
            json.dumps(
                {
                    "schema_version": "memova_input_source_index_v1",
                    "updated_at": now,
                    "meetings": [],
                    "imports": [],
                    "attachments": [],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
    ]
    files.extend(FileSpec(path, content, machine=True) for path, content in input_root_schema_specs().items())
    if prefix:
        return [FileSpec(f"{prefix}/{spec.path}", spec.content, spec.machine) for spec in files]
    return files


def input_root_readme(*, relative_path: str) -> str:
    return markdown(
        f"""# Memova Raw Input Root

This folder is the Memova-owned raw input layer for a user-owned knowledge base.
Its relative path is `{relative_path}`.

Memova V1 writes source material here so the user's own LLM wiki, Obsidian workflow, Codex workflow,
Claude Code workflow, or future Memova compiler can decide how to extract, compress, classify, and
move knowledge into downstream folders. Memova does not treat this folder as curated memory.

## What Memova Writes

Meeting packets are written under `meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/`.
Each packet is append-or-replace source material for one meeting. A packet can contain:

```text
README.md
manifest.json
metadata.json
transcript.md
transcript.json
final_note.md
final_note.json
raw_user_note.md
raw_user_note.json
ocr/
  imports.json
  <ocr_import_id>/
    manifest.json
    text.md
    pages.json
    pages/
      page-001.md
    files/
      page-001.png
attachments/
  attachments.json
  <attachment_id>.<ext>
images/
  images.json
  <analysis_image_id>.<ext>
media/
  audio_manifest.json
hashes.json
```

The canonical image folder is `images/`. Older V0 packets may contain `analysis_images/`; treat
that as the same raw analysis-image source area and do not rewrite it unless a migration is
explicitly requested.

The canonical OCR page binary folder is `ocr/<ocr_import_id>/files/`, with optional page markdown
under `ocr/<ocr_import_id>/pages/`. Older V0 packets may place page binaries directly under
`ocr/<ocr_import_id>/pages/`; readers should tolerate both shapes.

## What Memova Does Not Write

- Memova does not organize `wiki/`, `projects/`, `daily/`, or other downstream knowledge folders in
  V1.
- Memova does not save audio files by default. It writes `media/audio_manifest.json` so apps and
  agents can understand audio provenance and retention without expecting the audio file to exist.
- Memova does not turn meeting content into long-term memory without a later user-confirmed
  extraction workflow.

## How Agents Should Use This Folder

Use this folder as evidence, not as truth after interpretation. When an agent creates wiki pages,
project updates, action lists, or summaries from these packets, it should cite the packet path and
the specific source file it used. Keep raw source files stable so future compilers can re-run from
the same evidence.

See `AGENTS.md` for operating rules and `schemas/*.schema.md` for the file contracts.
"""
    )


def input_root_agents(*, relative_path: str) -> str:
    return markdown(
        f"""# Agent Rules For Memova Raw Input

Scope: this file applies to the Memova raw input root at `{relative_path}` and every meeting packet
inside it.

## Core Rules

- Treat this folder as source evidence, not curated long-term knowledge.
- Do not rewrite `transcript.*`, `raw_user_note.*`, OCR text, attachment files, image files,
  `metadata.json`, `manifest.json`, or `hashes.json` unless the user explicitly asks for a repair or
  migration.
- Do not delete packets or source files just because a downstream wiki/project page has been
  generated.
- No memory without source. Any long-term memory derived from this folder must cite a packet path and
  source file.
- No action without evidence. Action candidates derived from this folder must cite transcript,
  final-note, raw-note, OCR, attachment, or image evidence.
- No external write without confirmation. Email, calendar, repo, docs, Slack, Linear, or other
  external changes need user approval unless a separate approved automation explicitly says
  otherwise.

## Reading Order

1. Read `manifest.json` first to understand roles, write modes, and asset availability.
2. Read `metadata.json` for meeting identity, title, time range, status, note ids, and processing
   metadata.
3. Read `transcript.md` or `transcript.json` for source speech.
4. Read `raw_user_note.*`, OCR files, attachments, and images as user-provided context.
5. Read `final_note.*` as a Memova-compiled view that still needs source citation for durable
   knowledge.
6. Check `hashes.json` before assuming local files are unchanged.

## Updating Derived Knowledge

When creating or updating downstream wiki/project/daily files:

- preserve the original packet files;
- include source links such as
  `inbox/memova/meetings/2026/05/2026-05-21-example-meeting-<meeting_id>/transcript.md`;
- distinguish confirmed meeting facts from model inference;
- keep uncertain OCR, ASR corrections, and failed imports marked as uncertain;
- prefer small append/update patches over reorganizing a user's whole vault.

## Conflict Handling

If a packet has both legacy and canonical shapes, read both and preserve both. If two files disagree,
prefer user-entered raw notes over reviewed OCR, reviewed OCR over high-confidence automatic OCR,
automatic OCR over final transcript, final transcript over realtime ASR drafts, and all source
evidence over model inference.
"""
    )


def input_root_schema_specs() -> dict[str, str]:
    return {
        "schemas/meeting_packet.schema.md": meeting_packet_schema(),
        "schemas/transcript.schema.md": transcript_schema(),
        "schemas/note.schema.md": note_schema(),
        "schemas/ocr.schema.md": ocr_schema(),
        "schemas/attachment.schema.md": attachment_schema(),
    }


def meeting_packet_schema() -> str:
    return markdown(
        """# Meeting Packet Schema

This schema describes one Memova meeting packet under:

```text
meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/
```

The packet is raw input plus stable Memova processing output. It is designed to be copied into a
user-owned file system and later consumed by LLM wiki compilers, local apps, and agents.

## Required Packet Files

- `README.md`: human-readable packet overview.
- `manifest.json`: machine index of every generated file and downloadable asset. Agents should read
  this first.
- `metadata.json`: meeting, note, transcript, processing, and source metadata.
- `transcript.md`: human-readable final transcript. This is not realtime draft text.
- `transcript.json`: structured transcript with machine-readable timing/speaker metadata when
  available.
- `final_note.md`: Memova compiled final note in Markdown.
- `final_note.json`: structured final note for apps and agents.
- `raw_user_note.md`: user-entered notes and source notes in Markdown.
- `raw_user_note.json`: structured raw-user-note data.
- `hashes.json`: checksums for packet integrity and sync comparison.

## Conditional Packet Folders

- `ocr/`: OCR imports from handwritten notes, screenshots, documents, or other image-derived text.
  When OCR exists, include an index such as `ocr/imports.json` plus one folder per import.
- `attachments/`: non-image attachments plus `attachments.json`.
- `images/`: analysis images plus `images.json`. Older packets may use `analysis_images/`.
- `media/`: audio provenance, usually `audio_manifest.json`; audio files are not saved by default.

## Write Mode

iOS should write packet files from the backend sync package using the write mode in
`manifest.json`. V0 normally uses replace semantics for generated packet files. Agents should not
hand-edit packet source files unless repairing a broken sync with user approval.

## Evidence Rules

Downstream pages may quote or summarize this packet only with source attribution. A durable claim,
memory, action, decision, or project update should cite one or more packet files and preserve the
meeting id or packet path.
"""
    )


def transcript_schema() -> str:
    return markdown(
        """# Transcript Schema

`transcript.md` and `transcript.json` store the stable post-meeting transcript. Realtime captions or
draft ASR text should not be treated as final transcript evidence unless explicitly labeled.

## `transcript.md`

Markdown is for human and LLM reading. It should preserve speaker labels and temporal order when
available. It may include section headings for readability, but it should not add facts that were
not present in the speech or reviewed transcript source.

## `transcript.json`

JSON is for deterministic app and agent access. Recommended fields include:

- meeting id and transcript id;
- language and provider metadata;
- utterance or segment list;
- speaker label or speaker id when available;
- start and end offsets when available;
- calibrated or corrected transcript text;
- confidence, provenance, and processing metadata when available.

## Update Rules

If a transcript is regenerated, replace both Markdown and JSON together and update `manifest.json`
and `hashes.json`. Do not mix final transcript text with inferred summary content.
"""
    )


def note_schema() -> str:
    return markdown(
        """# Note Schema

This schema covers `final_note.*` and `raw_user_note.*` inside a meeting packet.

## `raw_user_note.md` and `raw_user_note.json`

Raw user notes are user-authored or user-captured source material. They may include typed notes,
quick thoughts, imported text, or reviewed OCR-derived notes. Treat them as source evidence and do
not rewrite them into polished prose inside the packet.

## `final_note.md` and `final_note.json`

Final notes are Memova-compiled outputs derived from transcript, raw notes, OCR, attachments, and
other packet evidence. They are useful for reading and search, but they are still derived content.
Downstream durable memory should cite both the final note and the original source files when
possible.

## Grounding Rules

- Ordinary final-note sections should compress evidence rather than invent external facts.
- Raw-note response sections may include interpretation, but should distinguish meeting-grounded
  content from external expansion.
- Action-like text in a final note is not automatically a confirmed action. Confirmed actions need
  explicit user confirmation in the product workflow or a later approved agent workflow.
"""
    )


def ocr_schema() -> str:
    return markdown(
        """# OCR Schema

OCR data records text extracted from images, handwritten notes, screenshots, or scanned pages.

Recommended structure:

```text
ocr/
  imports.json
  <ocr_import_id>/
    manifest.json
    text.md
    pages.json
    pages/
      page-001.md
    files/
      page-001.png
```

## Files

- `ocr/imports.json`: packet-level OCR import index. Include success and failure states so the app
  can show import status without scanning every folder.
- `<ocr_import_id>/manifest.json`: import-level metadata, source ids, status, processing timestamps,
  and failure information when relevant.
- `<ocr_import_id>/text.md`: reviewed or calibrated OCR text for human and LLM reading.
- `<ocr_import_id>/pages.json`: structured page metadata, raw OCR output, uncertain spans, page
  numbers, and asset references.
- `<ocr_import_id>/pages/page-001.md`: optional page-level text for LLM-friendly reading.
- `<ocr_import_id>/files/page-001.png`: source image or page binary when saved.

Older V0 packets may store page binaries under `pages/page-001.png` without a separate `files/`
folder. Readers should tolerate this shape. New writers should prefer the structure above.

## Authority And Uncertainty

Reviewed OCR is stronger evidence than automatic OCR. Automatic OCR uncertain spans, failed pages,
and model-inferred corrections must remain visible in JSON metadata and should not be promoted to
confirmed facts without user review.
"""
    )


def attachment_schema() -> str:
    return markdown(
        """# Attachment And Image Schema

This schema covers generic attachments and analysis images stored inside a meeting packet.

## Attachments

```text
attachments/
  attachments.json
  <attachment_id>.<ext>
```

`attachments.json` should list each attachment id, filename, extension, content type, byte size,
checksum when available, source API path or provenance, and relative file path. If there are no
attachments, keep `attachments.json` with an empty list so apps do not need to guess.

## Images

```text
images/
  images.json
  <analysis_image_id>.<ext>
```

`images.json` should list analysis images that are useful as source evidence. Older packets may use
`analysis_images/`; readers should treat it as a legacy alias for `images/`.

## Agent Rules

Agents may summarize attachments and images only after checking the metadata and source files. If a
binary asset is unavailable, expired, or not downloaded, say that explicitly rather than inventing
visual evidence.
"""
    )


def root_file_specs(setup: dict[str, Any], *, now: str) -> list[FileSpec]:
    return [
        FileSpec(
            "README.md",
            root_readme(now=now),
            machine=True,
        ),
        FileSpec(
            "AGENTS.md",
            root_agents(),
            machine=True,
        ),
        FileSpec(
            "inbox/README.md",
            root_folder_readme(
                title="Inbox",
                body=(
                    "Low-friction input area. Memova writes its raw meeting packets under "
                    "`inbox/memova/`. Other inbox files can belong to the user or other tools."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "sources/README.md",
            root_folder_readme(
                title="Sources",
                body=(
                    "Reserved for user-managed or future agent-managed source material outside the "
                    "Memova raw meeting input root. Memova V1 does not write here."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "wiki/README.md",
            root_folder_readme(
                title="Wiki",
                body=(
                    "Reserved for curated long-term knowledge pages. Pages here should cite source "
                    "packets or other evidence. Memova V1 does not auto-create wiki pages."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "projects/README.md",
            root_folder_readme(
                title="Projects",
                body=(
                    "Reserved for project-specific summaries, decisions, actions, and outputs that "
                    "the user or a later confirmed agent workflow derives from sources."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "daily/README.md",
            root_folder_readme(
                title="Daily",
                body=(
                    "Reserved for daily notes, plans, and reviews. Memova V1 does not write daily "
                    "notes automatically."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "outputs/README.md",
            root_folder_readme(
                title="Outputs",
                body=(
                    "Reserved for finished artifacts such as reports, specs, articles, decks, or "
                    "other deliverables derived from the knowledge base."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "archive/README.md",
            root_folder_readme(
                title="Archive",
                body=(
                    "Reserved for inactive material. Archive content should stay searchable but "
                    "should not drive current project context unless explicitly selected."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "schemas/README.md",
            root_folder_readme(
                title="Schemas",
                body=(
                    "Reserved for user-level or future vault-level schemas. The active Memova V1 "
                    "raw input schemas live in `inbox/memova/schemas/`."
                ),
            ),
            machine=True,
        ),
        FileSpec(
            "_memova/manifest.json",
            json.dumps(root_manifest(setup, now=now), indent=2, ensure_ascii=False) + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/vault_mapping.json",
            json.dumps(
                {
                    "schema_version": "memova_vault_mapping_v1",
                    "updated_at": now,
                    "memova_input_root": INPUT_ROOT_RELATIVE_PATH,
                    "semantic_roots": {
                        "inbox": "inbox",
                        "memova_input_root": INPUT_ROOT_RELATIVE_PATH,
                        "sources": "sources",
                        "wiki": "wiki",
                        "projects": "projects",
                        "daily": "daily",
                        "outputs": "outputs",
                        "archive": "archive",
                        "_memova": "_memova",
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/sync_state.json",
            json.dumps(
                {
                    "schema_version": "memova_vault_sync_state_v1",
                    "updated_at": now,
                    "last_successful_sync_at": None,
                    "conflicts": [],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
    ]


def root_readme(*, now: str) -> str:
    return markdown(
        f"""# Memova Vault

This is a user-owned Memova knowledge base initialized by Codex for Memova.

Memova V1 writes complete raw meeting packets only under `inbox/memova/`. The other folders are
intentionally empty starter surfaces for the user, Obsidian, Codex, Claude Code, Cursor, or future
Memova compiler workflows.

## Structure

```text
inbox/
  memova/
    meetings/
    imports/
    attachments/
    schemas/
    _memova/
sources/
wiki/
projects/
daily/
outputs/
archive/
schemas/
_memova/
```

## Ownership Model

- `inbox/memova/` is the Memova raw input root.
- `sources/`, `wiki/`, `projects/`, `daily/`, `outputs/`, `archive/`, and root `schemas/` are
  user-owned surfaces.
- `_memova/` contains machine-readable setup and sync metadata.

## V1 Scope

Memova captures and compiles meeting source material, then syncs that source material into the raw
input root. It does not automatically classify meetings into projects, update long-term wiki pages,
or create durable memories in V1.

Agents should use `inbox/memova/` as evidence. Any durable wiki/project/action output created later
should cite the original meeting packet path and source file.

Created by Memova setup on {now}.
"""
    )


def root_agents() -> str:
    return markdown(
        """# Agent Rules For This Memova Vault

These rules apply to the whole vault. More specific rules for Memova raw meeting packets live in
`inbox/memova/AGENTS.md`.

## Core Rules

- Treat `inbox/memova/` as source evidence, not curated long-term memory.
- Do not reorganize or rename user-authored folders without explicit user approval.
- Do not move raw Memova packets out of `inbox/memova/meetings/` unless the user requests a
  migration.
- No memory without source. Durable wiki/project pages must cite the source packet and source file.
- No action without evidence. Action candidates must reference meeting evidence.
- No external write without confirmation.

## Recommended Agent Flow

1. Read `inbox/memova/README.md` and `inbox/memova/AGENTS.md`.
2. Use `inbox/memova/schemas/*.schema.md` to understand packet contracts.
3. Read packet `manifest.json` before reading packet content.
4. Create derived wiki/project/daily/output files only after the user asks for that workflow.
5. Preserve original raw source packets for future reprocessing.
"""
    )


def root_folder_readme(*, title: str, body: str) -> str:
    return markdown(
        f"""# {title}

{body}

This folder is part of the Memova LLM wiki skeleton. In V1, Memova's automatic writes are limited
to the raw input root at `inbox/memova/`.
"""
    )


def build_dirs(setup: dict[str, Any]) -> list[str]:
    if is_existing_vault_setup(setup):
        return list(INPUT_ROOT_DIRS)
    return list(NEW_VAULT_DIRS)


def build_file_specs(setup: dict[str, Any], *, target_root: Path, now: str | None = None) -> list[FileSpec]:
    now = now or utc_now_iso()
    relative_path = memova_input_root_relative_path(setup, target_root)
    if is_existing_vault_setup(setup):
        return input_root_file_specs(setup, now=now, relative_path=relative_path)
    return root_file_specs(setup, now=now) + input_root_file_specs(
        setup,
        now=now,
        relative_path=INPUT_ROOT_RELATIVE_PATH,
        prefix=INPUT_ROOT_RELATIVE_PATH,
    )


def create_plan(
    *,
    target_root: Path,
    setup: dict[str, Any],
    allow_non_icloud: bool = False,
    allow_existing_nonempty: bool = False,
    overwrite_machine_files: bool = False,
) -> dict[str, Any]:
    target_root = expand_path(str(target_root))
    mode = setup_mode(setup)
    storage_target = setup.get("storage_target") or "icloud_drive"
    exists = target_root.exists()
    nonempty = exists and any(target_root.iterdir())
    under_icloud = path_under_icloud(target_root)
    warnings: list[str] = []
    errors: list[str] = []
    source_vault_paths = extract_source_vault_paths(setup)
    suggested_existing_vault_target = None

    if mode not in ALLOWED_SETUP_MODES:
        errors.append(
            "Unsupported setup_mode. Use create_new_vault or connect_existing_vault.",
        )
    if storage_target == "icloud_drive" and not under_icloud:
        message = "Target path is not under a detected iCloud Drive root."
        if allow_non_icloud:
            warnings.append(message)
        else:
            errors.append(message)
    if mode == "create_new_vault" and nonempty and not allow_existing_nonempty:
        errors.append("Target root already exists and is not empty.")
    if mode == "connect_existing_vault" and source_vault_paths:
        target_resolved = resolved(target_root)
        containing_sources = [source for source in source_vault_paths if path_inside(source, target_resolved)]
        if not containing_sources:
            suggested_existing_vault_target = str(
                suggested_existing_input_target(setup, source_vault_paths[0]),
            )
            errors.append(
                "For connect_existing_vault, target root must be a Memova input-root child folder "
                "inside the supplied existing vault path."
            )
        else:
            exact_sources = [source for source in containing_sources if resolved(source) == target_resolved]
            if exact_sources:
                suggested_existing_vault_target = str(
                    suggested_existing_input_target(setup, exact_sources[0]),
                )
                errors.append(
                    "For connect_existing_vault, target root cannot be the existing vault root "
                    f"itself. Use a Memova input-root child folder such as "
                    f"{suggested_existing_vault_target}."
                )

    dirs = build_dirs(setup)
    files = build_file_specs(setup, target_root=target_root)
    operations: list[dict[str, Any]] = []
    for directory in dirs:
        path = safe_join(target_root, directory)
        operations.append(
            {
                "op": "mkdir",
                "path": str(path),
                "relative_path": directory,
                "status": "exists" if path.exists() else "create",
            },
        )
    for spec in files:
        path = safe_join(target_root, spec.path)
        exists_file = path.exists()
        should_overwrite = bool(spec.machine and overwrite_machine_files)
        status = "overwrite" if exists_file and should_overwrite else "skip" if exists_file else "create"
        operations.append(
            {
                "op": "write_file",
                "path": str(path),
                "relative_path": spec.path,
                "status": status,
                "machine_file": spec.machine,
                "bytes": len(spec.content.encode("utf-8")),
            },
        )

    relative_path = memova_input_root_relative_path(setup, target_root)
    target_kind = "memova_input_root" if mode == "connect_existing_vault" else "memova_vault"
    plan_target_root = str(resolved(target_root))
    plan = {
        "schema_version": "memova_vault_operation_plan_v1",
        "target_root": plan_target_root,
        "setup_mode": mode,
        "storage_target": storage_target,
        "vault_template_version": setup.get("vault_template_version") or TEMPLATE_VERSION,
        "target_kind": target_kind,
        "under_detected_icloud_root": under_icloud,
        "target_exists": exists,
        "target_nonempty": nonempty,
        "vault_manifest_id": manifest_id(setup),
        "input_root_manifest_id": input_root_manifest_id(setup),
        "memova_input_root_relative_path": relative_path,
        "source_vault_paths": [str(path) for path in source_vault_paths],
        "suggested_existing_vault_target": suggested_existing_vault_target,
        "warnings": warnings,
        "errors": errors,
        "operations": operations,
        "summary": summarize_operations(operations),
    }
    plan["ios_folder_binding_hints"] = ios_folder_binding_hints(plan)
    return plan


def ios_folder_binding_hints(plan: dict[str, Any]) -> dict[str, Any]:
    target_root = Path(plan["target_root"])
    target_kind = plan.get("target_kind")
    input_root_relative_path = str(plan.get("memova_input_root_relative_path") or ".")
    if target_kind == "memova_vault":
        vault_root = target_root
        input_root = safe_join(vault_root, input_root_relative_path)
    else:
        input_root = target_root
        vault_root = source_vault_root_for_target(plan, target_root)

    icloud_relative_vault_path = relative_to_icloud(vault_root) if vault_root is not None else None
    icloud_relative_input_root_path = relative_to_icloud(input_root)
    input_root_manifest_relative_path = (
        join_relative(icloud_relative_input_root_path, "_memova/manifest.json")
        if icloud_relative_input_root_path is not None
        else None
    )
    vault_relative_manifest_path = (
        join_relative(input_root_relative_path, "_memova/manifest.json")
        if input_root_relative_path != "."
        else "_memova/manifest.json"
    )
    candidates = [
        {
            "kind": "selected_folder_is_input_root",
            "manifest_relative_path": "_memova/manifest.json",
        },
    ]
    if target_kind == "memova_vault":
        candidates.append(
            {
                "kind": "selected_folder_is_new_vault_root",
                "manifest_relative_path": join_relative(
                    input_root_relative_path,
                    "_memova/manifest.json",
                ),
            }
        )
    elif input_root_relative_path != ".":
        candidates.append(
            {
                "kind": "selected_folder_is_existing_vault_root",
                "manifest_relative_path": vault_relative_manifest_path,
            }
        )
    if input_root_manifest_relative_path:
        candidates.append(
            {
                "kind": "selected_folder_is_icloud_drive_root",
                "manifest_relative_path": input_root_manifest_relative_path,
            }
        )
    return {
        "schema_version": "memova_ios_folder_binding_hints_v1",
        "storage_target": plan.get("storage_target") or "icloud_drive",
        "target_kind": target_kind,
        "authorization_strategy": "user_selects_ancestor_then_app_resolves_relative_manifest",
        "icloud_relative_vault_path": icloud_relative_vault_path,
        "icloud_relative_input_root_path": icloud_relative_input_root_path,
        "memova_input_root_relative_path": input_root_relative_path,
        "input_root_manifest_relative_path": input_root_manifest_relative_path,
        "vault_relative_input_root_manifest_path": vault_relative_manifest_path,
        "expected_vault_manifest_id": plan.get("vault_manifest_id"),
        "expected_input_root_manifest_id": plan.get("input_root_manifest_id"),
        "candidate_manifest_paths": candidates,
    }


def source_vault_root_for_target(plan: dict[str, Any], target_root: Path) -> Path | None:
    target = resolved(target_root)
    for raw_path in plan.get("source_vault_paths") or []:
        source = resolved(expand_path(str(raw_path)))
        if target == source or source in target.parents:
            return source
    return None

def summarize_operations(operations: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "mkdir_create": 0,
        "mkdir_exists": 0,
        "file_create": 0,
        "file_skip": 0,
        "file_overwrite": 0,
    }
    for op in operations:
        if op["op"] == "mkdir" and op["status"] == "create":
            summary["mkdir_create"] += 1
        elif op["op"] == "mkdir":
            summary["mkdir_exists"] += 1
        elif op["op"] == "write_file" and op["status"] == "create":
            summary["file_create"] += 1
        elif op["op"] == "write_file" and op["status"] == "overwrite":
            summary["file_overwrite"] += 1
        elif op["op"] == "write_file":
            summary["file_skip"] += 1
    return summary


def apply_plan(plan: dict[str, Any], setup: dict[str, Any], *, overwrite_machine_files: bool = False) -> dict[str, Any]:
    if plan.get("errors"):
        return {
            "status": "error",
            "errors": plan["errors"],
            "target_root": plan.get("target_root"),
        }
    target_root = Path(plan["target_root"])
    specs_by_path = {
        spec.path: spec for spec in build_file_specs(setup, target_root=target_root)
    }
    created_dirs: list[str] = []
    created_files: list[str] = []
    skipped_files: list[str] = []
    overwritten_files: list[str] = []

    for operation in plan["operations"]:
        path = Path(operation["path"])
        if operation["op"] == "mkdir":
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created_dirs.append(operation["relative_path"])
            continue
        if operation["op"] != "write_file":
            continue
        spec = specs_by_path[operation["relative_path"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not (spec.machine and overwrite_machine_files):
            skipped_files.append(operation["relative_path"])
            continue
        path.write_text(spec.content, encoding="utf-8")
        if operation["status"] == "overwrite":
            overwritten_files.append(operation["relative_path"])
        else:
            created_files.append(operation["relative_path"])

    return {
        "status": "ok",
        "target_root": str(target_root),
        "vault_manifest_id": plan["vault_manifest_id"],
        "manifest_id": plan["vault_manifest_id"],
        "input_root_manifest_id": plan["input_root_manifest_id"],
        "memova_input_root_relative_path": plan["memova_input_root_relative_path"],
        "ios_folder_binding_hints": plan.get("ios_folder_binding_hints", {}),
        "selected_by": "codex_suggested_user_confirmed",
        "target_path_summary": plan["target_root"],
        "created_dir_count": len(created_dirs),
        "created_file_count": len(created_files),
        "skipped_file_count": len(skipped_files),
        "overwritten_file_count": len(overwritten_files),
        "created_dirs": created_dirs,
        "created_files": created_files,
        "skipped_files": skipped_files,
        "overwritten_files": overwritten_files,
    }


def validate_vault(path: Path) -> dict[str, Any]:
    root = expand_path(str(path))
    is_new_vault = safe_join(root, f"{INPUT_ROOT_RELATIVE_PATH}/_memova/manifest.json").is_file()
    missing_roots: list[str] = []
    missing_machine_files: list[str] = []
    invalid_required_files: list[dict[str, Any]] = []
    input_root = safe_join(root, INPUT_ROOT_RELATIVE_PATH) if is_new_vault else root

    if is_new_vault:
        for root_path in NEW_VAULT_REQUIRED_ROOTS:
            target = safe_join(root, root_path.rstrip("/"))
            if not target.exists():
                missing_roots.append(root_path)
        invalid_required_files.extend(validate_doc_content(root, NEW_VAULT_DOC_CHECKS, min_chars=120))
        for relative_path in (
            "_memova/manifest.json",
            "_memova/vault_mapping.json",
            "_memova/sync_state.json",
        ):
            if not safe_join(root, relative_path).is_file():
                missing_machine_files.append(relative_path)

    for relative_path in INPUT_ROOT_REQUIRED_FILES:
        if not safe_join(input_root, relative_path).is_file():
            missing_machine_files.append(
                f"{INPUT_ROOT_RELATIVE_PATH}/{relative_path}" if is_new_vault else relative_path,
            )
    input_doc_issues = validate_doc_content(input_root, INPUT_ROOT_DOC_CHECKS, min_chars=240)
    if is_new_vault:
        invalid_required_files.extend(
            {
                **issue,
                "relative_path": f"{INPUT_ROOT_RELATIVE_PATH}/{issue['relative_path']}",
            }
            for issue in input_doc_issues
        )
    else:
        invalid_required_files.extend(input_doc_issues)

    manifest_path = safe_join(input_root, "_memova/manifest.json")
    manifest: dict[str, Any] | None = None
    manifest_error: str | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            manifest_error = str(exc)

    status = "ok"
    if missing_roots or missing_machine_files or invalid_required_files or manifest_error:
        status = "fail"

    return {
        "schema_version": "memova_vault_validation_v1",
        "status": status,
        "path": str(resolved(root)),
        "target_kind": "memova_vault" if is_new_vault else "memova_input_root",
        "memova_input_root_path": str(resolved(input_root)),
        "memova_input_root_relative_path": INPUT_ROOT_RELATIVE_PATH
        if is_new_vault
        else manifest.get("memova_input_root_relative_path", ".")
        if manifest
        else ".",
        "missing_roots": missing_roots,
        "missing_machine_files": missing_machine_files,
        "invalid_required_files": invalid_required_files,
        "vault_manifest_id": manifest_id_from_root(root) if is_new_vault else None,
        "input_root_manifest_id": manifest.get("manifest_id") if manifest else None,
        "manifest_id": manifest.get("manifest_id") if manifest else None,
        "manifest_error": manifest_error,
    }


def validate_doc_content(
    root: Path,
    checks: dict[str, list[str]],
    *,
    min_chars: int,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for relative_path, keywords in checks.items():
        path = safe_join(root, relative_path)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        stripped = text.strip()
        if len(stripped) < min_chars:
            issues.append(
                {
                    "relative_path": relative_path,
                    "code": "thin_required_doc",
                    "char_count": len(stripped),
                    "min_chars": min_chars,
                }
            )
            continue
        missing_keywords = [keyword for keyword in keywords if keyword not in text]
        if missing_keywords:
            issues.append(
                {
                    "relative_path": relative_path,
                    "code": "missing_required_doc_keywords",
                    "missing_keywords": missing_keywords,
                }
            )
    return issues


def manifest_id_from_root(root: Path) -> str | None:
    manifest_path = safe_join(root, "_memova/manifest.json")
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = manifest.get("manifest_id")
    return value if isinstance(value, str) else None


def inspect_tree(path: Path, *, max_depth: int = 3, max_entries: int = 500) -> dict[str, Any]:
    root = expand_path(str(path))
    entries: list[dict[str, Any]] = []
    root_resolved = resolved(root)
    if not root.exists():
        return {
            "status": "not_found",
            "path": str(root_resolved),
            "entries": entries,
            "raw_input_candidates": [],
        }
    for current_root, dirnames, filenames in os.walk(root):
        current = Path(current_root)
        relative = current.relative_to(root)
        depth = 0 if str(relative) == "." else len(relative.parts)
        if depth >= max_depth:
            dirnames[:] = []
        for dirname in sorted(dirnames):
            rel = str((relative / dirname) if str(relative) != "." else Path(dirname))
            entries.append({"type": "dir", "path": rel})
            if len(entries) >= max_entries:
                break
        if len(entries) >= max_entries:
            break
        for filename in sorted(filenames):
            rel = str((relative / filename) if str(relative) != "." else Path(filename))
            entries.append({"type": "file", "path": rel})
            if len(entries) >= max_entries:
                break
        if len(entries) >= max_entries:
            break

    manifest_path = safe_join(root, "_memova/manifest.json")
    input_manifest_path = safe_join(root, f"{INPUT_ROOT_RELATIVE_PATH}/_memova/manifest.json")
    obsidian_path = root / ".obsidian"
    return {
        "status": "ok",
        "path": str(root_resolved),
        "entry_count": len(entries),
        "truncated": len(entries) >= max_entries,
        "has_memova_vault_manifest": manifest_path.exists(),
        "has_memova_input_root_manifest": input_manifest_path.exists(),
        "has_obsidian_config": obsidian_path.exists(),
        "raw_input_candidates": raw_input_candidates(root, max_depth=2),
        "entries": entries,
    }
