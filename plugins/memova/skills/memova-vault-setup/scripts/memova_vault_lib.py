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
DEFAULT_NEW_VAULT_FOLDER_NAME = "Memova Vault"
ALLOWED_SETUP_MODES = {"create_new_vault", "connect_existing_vault"}

NEW_VAULT_DIRS = [
    "inbox/memova/schemas",
    "inbox/memova/meetings",
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
    "INDEX.md",
    "schemas/meeting_packet.schema.md",
    "schemas/manifest.schema.md",
    "schemas/packet.schema.md",
    "schemas/asset.schema.md",
    "schemas/promotion.schema.md",
    "_memova/manifest.json",
    "_memova/input_root.json",
    "_memova/sync_state.json",
    "_memova/source_index.json",
]

SETUP_IDENTITY_FILE_PATHS = {
    "_memova/manifest.json",
    f"{INPUT_ROOT_RELATIVE_PATH}/_memova/manifest.json",
}

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
        "Memova Inbox Packet Format v1",
        "meetings/YYYY/MM",
        "sources.md",
        "promotion.json",
    ],
    "AGENTS.md": [
        "Agent Rules",
        "No memory without source",
        "No action without evidence",
        "Reading Order",
    ],
    "INDEX.md": [
        "Memova Inbox Index",
        "meetings/",
        "recent meeting packets",
    ],
    "schemas/meeting_packet.schema.md": [
        "Meeting Packet Schema",
        "sources.md",
        "note.md",
        "promotion.json",
    ],
    "schemas/manifest.schema.md": [
        "Manifest Schema",
        "files",
        "assets_summary",
        "processing",
    ],
    "schemas/packet.schema.md": [
        "Packet JSON Schema",
        "sources",
        "note",
        "processing",
    ],
    "schemas/asset.schema.md": [
        "Asset Manifest Schema",
        "asset_id",
        "role",
        "source_ref",
    ],
    "schemas/promotion.schema.md": [
        "Promotion Schema",
        "promotion_status",
        "not_started",
        "promoted_items",
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


def load_setup_json(path: str | None, *, required: bool = False) -> dict[str, Any]:
    if not path:
        if required:
            raise ValueError(
                "A Memova setup package JSON file is required. Retrieve it from "
                "list_pending_knowledge_base_setups/get_knowledge_base_setup_context before planning or creating files."
            )
        return {}
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if "setup_package" in data and isinstance(data["setup_package"], dict):
        setup = data["setup_package"]
    else:
        setup = data
    if required:
        errors = setup_package_errors(setup)
        if errors:
            raise ValueError("Invalid Memova setup package: " + "; ".join(errors))
    return setup


def setup_package_errors(setup: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if setup.get("schema_version") != SETUP_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SETUP_SCHEMA_VERSION}")
    if setup_mode(setup) not in ALLOWED_SETUP_MODES:
        errors.append("setup_mode must be create_new_vault or connect_existing_vault")
    if not isinstance(setup.get("target_path_hints") or {}, dict):
        errors.append("target_path_hints must be an object when provided")
    if not isinstance(setup.get("source_path_hints") or {}, dict):
        errors.append("source_path_hints must be an object when provided")
    return errors


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


def detect_icloud_roots(setup: dict[str, Any] | None = None) -> list[dict[str, str]]:
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

    setup = setup or {}
    new_vault_folder = new_vault_folder_name(setup)
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
                "recommended_new_vault": str(expanded / new_vault_folder),
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


def is_setup_identity_file(relative_path: str) -> bool:
    normalized = relative_path.strip().replace("\\", "/")
    return normalized in SETUP_IDENTITY_FILE_PATHS


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


def new_vault_folder_name(setup: dict[str, Any]) -> str:
    hints = setup.get("target_path_hints") or {}
    if isinstance(hints, dict):
        for key in (
            "desired_vault_folder_name",
            "desired_vault_name",
            "desired_input_folder_name",
            "memova_folder_name",
            "desired_memova_folder_name",
        ):
            value = hints.get(key)
            if isinstance(value, str) and value.strip():
                return safe_component(value)
    return DEFAULT_NEW_VAULT_FOLDER_NAME


def suggested_new_vault_target(setup: dict[str, Any]) -> Path | None:
    for candidate in detect_icloud_roots(setup):
        if candidate.get("exists"):
            return resolved(Path(candidate["recommended_new_vault"]))
    return None


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
        FileSpec("INDEX.md", input_root_index(), machine=True),
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
                    "packet_format_version": "memova_meeting_packet_v1",
                    "packet_core_files": [
                        "README.md",
                        "manifest.json",
                        "sources.md",
                        "note.md",
                        "packet.json",
                        "promotion.json",
                        "assets/manifest.json",
                    ],
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
                    "assets": [],
                    "promotions": [],
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

This folder is the Memova-owned raw input layer for a user-owned knowledge base. Its relative path
is `{relative_path}`.

This root uses **Memova Inbox Packet Format v1**. It is an LLM Wiki-compatible inbox/staging layer,
not the user's long-term wiki. Memova writes meeting packets here; the user's own workflow or a
future approved Memova compiler can later promote stable information into `wiki/`, `projects/`,
`daily/`, or other long-term folders.

## What Memova Writes

Meeting packets are written under `meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/`.
Each packet is source evidence plus Memova's processed note for one meeting:

```text
README.md
manifest.json
sources.md
note.md
packet.json
promotion.json
assets/
  manifest.json
  <asset_id>.<ext>
```

`sources.md` is the main LLM-readable evidence file. It can contain transcript text, raw user notes,
OCR text, attachment extracted text, and image descriptions with source ids and reliability labels.
`note.md` is Memova's processed inbox note. `packet.json` is the complete structured snapshot for
iOS and deterministic tools. `promotion.json` tracks whether any packet items have been promoted to
long-term knowledge. `assets/` stores binary files through stable asset ids.

## What Memova Does Not Write

- Memova does not organize `wiki/`, `projects/`, `daily/`, or other downstream knowledge folders in
  V1.
- Memova does not save audio files by default. Audio provenance is recorded in `packet.json` and
  `assets/manifest.json` when relevant.
- Memova does not turn meeting content into long-term memory without a later user-confirmed
  extraction workflow.

## How Agents Should Use This Folder

Use this folder as evidence, not as truth after interpretation. When an agent creates wiki pages,
project updates, action lists, or summaries from these packets, it should cite the packet path and
the specific source section or JSON pointer it used. Keep packet source files stable so future
compilers can re-run from the same evidence.

See `INDEX.md` for the packet index, `AGENTS.md` for operating rules, and `schemas/*.schema.md` for
the file contracts.
"""
    )


def input_root_agents(*, relative_path: str) -> str:
    return markdown(
        f"""# Agent Rules For Memova Raw Input

Scope: this file applies to the Memova raw input root at `{relative_path}` and every meeting packet
inside it.

## Core Rules

- Treat this folder as source evidence, not curated long-term knowledge.
- Do not rewrite `sources.md`, `packet.json`, asset files, or source metadata unless the user
  explicitly asks for a repair or migration.
- `note.md` is processed inbox output. It is useful context, but it is not long-term memory until an
  approved promotion workflow records that in `promotion.json`.
- Do not delete packets or source files just because a downstream wiki/project page has been
  generated.
- No memory without source. Any long-term memory derived from this folder must cite a packet path and
  source section such as `sources.md#transcript` or a JSON pointer in `packet.json`.
- No action without evidence. Action candidates derived from this folder must cite transcript,
  raw-note, OCR, attachment, image, or processed-note evidence.
- No external write without confirmation. Email, calendar, repo, docs, Slack, Linear, or other
  external changes need user approval unless a separate approved automation explicitly says
  otherwise.

## Reading Order

1. Read packet `README.md` to understand meeting identity and recommended order.
2. Read `manifest.json` to verify file roles, hashes, schema versions, and asset availability.
3. Read `note.md` for Memova's processed inbox note.
4. Read `sources.md` when evidence or quotes are needed.
5. Read `packet.json` only when structured details, ids, timestamps, or full app state are needed.
6. Read `promotion.json` before creating or updating downstream knowledge.
7. Read `assets/manifest.json` before opening binary assets.

## Updating Derived Knowledge

When creating or updating downstream wiki/project/daily files:

- preserve the original packet files;
- include source links such as
  `inbox/memova/meetings/2026/05/2026-05-21-example-meeting-<meeting_id>/sources.md#transcript`;
- distinguish confirmed meeting facts from model inference;
- keep uncertain OCR, ASR corrections, and failed imports marked as uncertain;
- update `promotion.json` only when a promotion workflow has explicitly succeeded;
- prefer small append/update patches over reorganizing a user's whole vault.

## Conflict Handling

If two sources disagree, prefer user-entered raw notes over reviewed OCR, reviewed OCR over
high-confidence automatic OCR, automatic OCR over final transcript, final transcript over realtime
ASR drafts, and all source evidence over model inference.
"""
    )


def input_root_index() -> str:
    return markdown(
        """# Memova Inbox Index

This index is the stable entry point for Memova meeting packets.

Meeting packets live under:

```text
meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/
```

## recent meeting packets

Memova and iOS may append lightweight links here in a later version. For V1, use the date-partitioned
`meetings/` folder and each packet's `manifest.json` to discover synced meetings.

## Packet Format

Each packet uses Memova Inbox Packet Format v1:

```text
README.md
manifest.json
sources.md
note.md
packet.json
promotion.json
assets/manifest.json
assets/<asset_id>.<ext>
```

Read `schemas/meeting_packet.schema.md` for the full contract.
"""
    )


def input_root_schema_specs() -> dict[str, str]:
    return {
        "schemas/meeting_packet.schema.md": meeting_packet_schema(),
        "schemas/manifest.schema.md": manifest_schema(),
        "schemas/packet.schema.md": packet_schema(),
        "schemas/asset.schema.md": asset_schema(),
        "schemas/promotion.schema.md": promotion_schema(),
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
- `manifest.json`: lightweight machine index of schema versions, files, hashes, assets, and
  processing status. Agents should read this before large files.
- `sources.md`: LLM-readable source material with transcript, raw notes, OCR text, attachment text,
  and image descriptions separated by source id and reliability.
- `note.md`: Memova processed inbox note. It is not long-term memory until promoted.
- `packet.json`: complete structured packet snapshot for iOS and deterministic tools.
- `promotion.json`: mutable promotion state for downstream wiki/project/action/memory workflows.
- `assets/manifest.json`: asset index for binary files.
- `assets/<asset_id>.<ext>`: optional OCR images, attachments, screenshots, analysis images,
  thumbnails, or other binary files.

## Write Mode

iOS should write packet files from the backend sync package using the write mode in
`manifest.json`. V1 normally uses replace semantics for generated packet files. Agents should not
hand-edit source files unless repairing a broken sync with user approval.

## Evidence Rules

Downstream pages may quote or summarize this packet only with source attribution. A durable claim,
memory, action, decision, or project update should cite one or more packet files and preserve the
meeting id or packet path.
"""
    )


def manifest_schema() -> str:
    return markdown(
        """# Manifest Schema

`manifest.json` is the lightweight machine-readable index for a meeting packet. It should not
contain transcript or note body text.

Required top-level fields:

- `schema_version`: `memova_meeting_packet_manifest_v1`.
- `packet_type`: `memova_meeting_packet`.
- `packet_schema_version`: `memova_meeting_packet_v1`.
- `meeting_id`, `packet_id`, `title`, `created_at`, `updated_at`, `status`.
- `files`: list of packet files with `path`, `role`, `sha256`, `size_bytes`, and `content_type`.
- `assets_summary`: count plus `manifest_path`.
- `processing`: transcription, summarization, OCR, asset, and promotion states.

Recommended file roles:

- `entry`: `README.md`
- `source_text`: `sources.md`
- `processed_note`: `note.md`
- `structured_packet`: `packet.json`
- `promotion_state`: `promotion.json`
- `asset_manifest`: `assets/manifest.json`

Use this file for fast completeness checks before reading larger Markdown or JSON files.
"""
    )


def packet_schema() -> str:
    return markdown(
        """# Packet JSON Schema

`packet.json` is the complete structured snapshot of a Memova meeting packet. It is for iOS,
desktop tools, deterministic sync, and agents that need precise ids or timestamps. LLMs should
usually read `note.md` and `sources.md` first.

Recommended top-level fields:

- `schema_version`: `memova_meeting_packet_v1`.
- `packet_type`: `memova_meeting_packet`.
- `meeting`: meeting id, title, time range, timezone, language, participants, status.
- `sources`: raw user notes, transcript segments, OCR pages, attachment extractions, image
  analyses, and audio provenance.
- `note`: Memova processed note fields, summary, sections, decisions, actions, open questions, and
  candidate memories when present.
- `assets`: asset records mirrored from `assets/manifest.json`.
- `processing`: transcription, summarization, OCR, asset, and sync status plus errors.
- `promotion`: summary of promotion status. Detailed mutable state lives in `promotion.json`.

`packet.json` should be treated as a generated snapshot. Avoid frequent manual edits; use
`promotion.json` for downstream state changes.
"""
    )


def asset_schema() -> str:
    return markdown(
        """# Asset Manifest Schema

`assets/manifest.json` indexes every binary or large external file stored in `assets/`.

Each asset should include:

- `asset_id`: stable id, not the original filename.
- `filename`: local filename under `assets/`.
- `original_filename`: optional user/source filename.
- `role`: one of `audio_recording`, `ocr_source_image`, `attachment`, `screenshot`,
  `whiteboard_image`, `analysis_image`, `thumbnail`, `exported_pdf`, or `derived_text`.
- `mime_type`, `size_bytes`, `sha256`.
- `source_ref`: JSON pointer or Markdown section that produced this asset.
- `derived_text_ref`: optional `sources.md` section containing extracted or analyzed text.
- `available_for_download`, `download_url_expires_at`, and source API metadata when applicable.

Use stable generated filenames like `asset_<id>.png` rather than user filenames as primary keys.
"""
    )


def promotion_schema() -> str:
    return markdown(
        """# Promotion Schema

`promotion.json` tracks whether information from an inbox packet has been promoted into long-term
wiki/project/action/memory surfaces.

Required fields:

- `schema_version`: `memova_promotion_v1`.
- `meeting_id`, `packet_id`.
- `promotion_status`: `not_started`, `partially_promoted`, `promoted`, or `rejected`.
- `items`: list of promoted or pending items.
- `promoted_items`: optional convenience list of promoted targets for quick app display.

Each item should include:

- `source_item_id`: stable id from `packet.json` or a generated source id.
- `source_ref`: `sources.md` anchor or `packet.json` pointer.
- `target_path`: destination wiki/project/action path when known.
- `status`: `pending_review`, `promoted`, `rejected`, or `superseded`.
- `promoted_at`, `promoted_by`, and `notes` when available.

V1 starts with `promotion_status: not_started` and an empty `items` list. Later workflows may update
this file without rewriting the full `packet.json`.
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
    INDEX.md
    meetings/
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
    suggested_new_vault_target_path = None

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
    if mode == "create_new_vault":
        desired_folder = new_vault_folder_name(setup)
        suggested = suggested_new_vault_target(setup)
        suggested_new_vault_target_path = str(suggested) if suggested is not None else None
        if safe_component(target_root.name) != desired_folder:
            hint = f" Use {suggested_new_vault_target_path}." if suggested_new_vault_target_path else ""
            errors.append(
                "For create_new_vault, target root folder must match the Memova setup package "
                f"desired new-vault folder '{desired_folder}'.{hint}"
            )
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
        should_overwrite = bool(
            spec.machine and (overwrite_machine_files or is_setup_identity_file(spec.path))
        )
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
        "suggested_new_vault_target": suggested_new_vault_target_path,
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
        should_overwrite = bool(
            spec.machine and (overwrite_machine_files or is_setup_identity_file(spec.path))
        )
        if path.exists() and not should_overwrite:
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
        "identity_validation": setup_identity_validation(target_root, setup),
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


def setup_identity_validation(path: Path, setup: dict[str, Any]) -> dict[str, Any]:
    root = expand_path(str(path))
    validation = validate_vault(root)
    setup_session_id = setup.get("setup_session_id")
    expected_vault_manifest_id = manifest_id(setup)
    expected_input_root_manifest_id = input_root_manifest_id(setup)
    target_kind = validation.get("target_kind")
    input_root = Path(str(validation.get("memova_input_root_path") or root))
    input_manifest_path = safe_join(input_root, "_memova/manifest.json")
    input_manifest, input_error = read_json_file(input_manifest_path)

    root_manifest_data: dict[str, Any] | None = None
    root_error: str | None = None
    if target_kind == "memova_vault":
        root_manifest_data, root_error = read_json_file(safe_join(root, "_memova/manifest.json"))

    mismatches: list[dict[str, Any]] = []

    def expect(field: str, expected: Any, actual: Any, *, path_label: str) -> None:
        if expected != actual:
            mismatches.append(
                {
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                    "path": path_label,
                }
            )

    if input_error:
        mismatches.append(
            {
                "field": "input_root_manifest",
                "expected": "valid_json",
                "actual": input_error,
                "path": str(input_manifest_path),
            }
        )
    else:
        input_manifest = input_manifest or {}
        expect(
            "manifest_id",
            expected_input_root_manifest_id,
            input_manifest.get("manifest_id"),
            path_label=str(input_manifest_path),
        )
        expect(
            "setup_session_id",
            setup_session_id,
            input_manifest.get("setup_session_id"),
            path_label=str(input_manifest_path),
        )
        expect(
            "vault_manifest_id",
            expected_vault_manifest_id,
            input_manifest.get("vault_manifest_id"),
            path_label=str(input_manifest_path),
        )

    if target_kind == "memova_vault":
        root_manifest_path = safe_join(root, "_memova/manifest.json")
        if root_error:
            mismatches.append(
                {
                    "field": "vault_manifest",
                    "expected": "valid_json",
                    "actual": root_error,
                    "path": str(root_manifest_path),
                }
            )
        else:
            root_manifest_data = root_manifest_data or {}
            expect(
                "manifest_id",
                expected_vault_manifest_id,
                root_manifest_data.get("manifest_id"),
                path_label=str(root_manifest_path),
            )
            expect(
                "setup_session_id",
                setup_session_id,
                root_manifest_data.get("setup_session_id"),
                path_label=str(root_manifest_path),
            )

    return {
        "schema_version": "memova_setup_identity_validation_v1",
        "status": "ok" if not mismatches else "fail",
        "setup_session_id": setup_session_id,
        "target_kind": target_kind,
        "expected_vault_manifest_id": expected_vault_manifest_id,
        "expected_input_root_manifest_id": expected_input_root_manifest_id,
        "actual_vault_manifest_id": (
            root_manifest_data.get("manifest_id")
            if isinstance(root_manifest_data, dict)
            else validation.get("vault_manifest_id")
        ),
        "actual_input_root_manifest_id": (
            input_manifest.get("manifest_id")
            if isinstance(input_manifest, dict)
            else validation.get("input_root_manifest_id")
        ),
        "mismatches": mismatches,
    }


def read_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, str(exc)


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
