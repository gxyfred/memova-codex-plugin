from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEMPLATE_VERSION = "memova_llm_wiki_v1"
SETUP_SCHEMA_VERSION = "knowledge_base_setup_v1"

SEMANTIC_ROOTS = [
    "README.md",
    "AGENTS.md",
    "sources/",
    "inbox/",
    "wiki/",
    "schemas/",
    "projects/",
    "daily/",
    "outputs/",
    "archive/",
    "_memova/",
]

BASE_DIRS = [
    "sources/meetings",
    "sources/captures",
    "sources/imports",
    "sources/attachments",
    "inbox/review",
    "inbox/captures",
    "wiki/people",
    "wiki/organizations",
    "wiki/projects",
    "wiki/topics",
    "wiki/decisions",
    "wiki/claims",
    "wiki/processes",
    "wiki/outputs",
    "schemas",
    "projects",
    "daily",
    "outputs/articles",
    "outputs/reports",
    "outputs/decks",
    "outputs/product_specs",
    "archive",
    "_memova/compression/project_summaries",
    "_memova/compression/session_summaries",
    "_memova/compression/following_context",
]

REQUIRED_MACHINE_FILES = [
    "_memova/manifest.json",
    "_memova/vault_mapping.json",
    "_memova/sync_state.json",
    "_memova/local_first_plan.md",
]

SCHEMA_FILES = {
    "schemas/page.schema.md": """# Page Schema

Required fields:
- `type`
- `title`
- `status`
- `sources`
- `updated_at`

Rules:
- Every long-term page must have a type.
- Important claims must link back to sources.
- Mark inferred content as inferred.
- Do not silently overwrite conflicting facts.
""",
    "schemas/source.schema.md": """# Source Page Schema

Required fields:
- `type: source`
- `source_id`
- `source_kind`
- `created_at`
- `evidence_path`

Rules:
- Sources are evidence. Do not rewrite source content to make it cleaner.
- Link compiled wiki claims back to source pages or source ids.
""",
    "schemas/wiki-page.schema.md": """# Wiki Page Schema

Required fields:
- `type`
- `title`
- `status`
- `sources`
- `last_reviewed_at`

Rules:
- Do not add long-term memory without a source.
- Mark inferred content as inferred.
- Preserve conflicting evidence instead of silently overwriting it.
""",
    "schemas/project.schema.md": """# Project Page Schema

Required fields:
- `type: project`
- `status`
- `goal`
- `people`
- `open_actions`
- `decisions`
- `risks`
- `sources`

Rules:
- Keep project summaries compressed and execution-oriented.
- Use `_context/L2_project_summary.md` as the default agent context.
""",
    "schemas/action.schema.md": """# Action Page Schema

Required fields:
- `type: action`
- `status`
- `owner`
- `evidence`
- `created_from`

Rules:
- No action without evidence.
- External writes require explicit user confirmation.
""",
    "schemas/meeting.schema.md": """# Meeting Page Schema

Required fields:
- `type: meeting`
- `meeting_id`
- `date`
- `source_files`
- `brief`
- `suggested_actions`
- `memory_candidates`

Rules:
- Meeting pages are source-adjacent summaries, not unrestricted long-term memory.
- Keep raw transcript and raw inputs under `sources/`.
""",
    "schemas/person.schema.md": """# Person Page Schema

Required fields:
- `type: person`
- `name`
- `relationship`
- `sources`

Rules:
- Store only useful, confirmed, non-sensitive context.
- Prefer project-relevant facts over personal trivia.
""",
    "schemas/organization.schema.md": """# Organization Page Schema

Required fields:
- `type: organization`
- `name`
- `relationship`
- `sources`

Rules:
- Store confirmed work-relevant context only.
- Link organization facts to source meetings or documents.
- Keep speculative relationship mapping out of confirmed sections.
""",
    "schemas/topic.schema.md": """# Topic Page Schema

Required fields:
- `type: topic`
- `title`
- `summary`
- `sources`

Rules:
- Use topic pages for reusable knowledge, not one-off meeting notes.
- Separate stable facts from open questions.
- Link important conclusions back to sources.
""",
    "schemas/decision.schema.md": """# Decision Page Schema

Required fields:
- `type: decision`
- `decision`
- `status`
- `made_at`
- `sources`

Rules:
- Record alternatives and reversals when evidence exists.
- Do not present tentative discussion as a confirmed decision.
""",
    "schemas/claim.schema.md": """# Claim Page Schema

Required fields:
- `type: claim`
- `claim`
- `confidence`
- `sources`

Rules:
- Claims must be traceable.
- Lower confidence when sources conflict or are incomplete.
""",
    "schemas/process.schema.md": """# Process Page Schema

Required fields:
- `type: process`
- `title`
- `steps`
- `owner`
- `sources`

Rules:
- Use process pages for reusable workflows.
- Keep steps actionable and versioned when they change.
- Cite the meeting, document, or decision that established the process.
""",
    "schemas/output.schema.md": """# Output Page Schema

Required fields:
- `type: output`
- `title`
- `status`
- `owner`
- `sources`

Rules:
- Use output pages for finished or planned artifacts.
- Link to the actual artifact location when available.
- Track source decisions that shaped the output.
""",
}


@dataclass(frozen=True)
class FileSpec:
    path: str
    content: str
    machine: bool = False


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


def safe_component(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[/:\\]+", "-", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^A-Za-z0-9 ._()&+-]", "", value)
    return value[:80].strip(" ._-") or "Untitled"


def extract_project_names(setup: dict[str, Any]) -> list[str]:
    preferences = setup.get("user_preferences") or {}
    names: list[str] = []
    for key in ("project_names", "projects", "active_projects"):
        value = preferences.get(key)
        if isinstance(value, str):
            names.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("project_name")
                    if isinstance(name, str):
                        names.append(name)
    primary = preferences.get("primary_project_name")
    if isinstance(primary, str):
        names.insert(0, primary)

    clean: list[str] = []
    seen: set[str] = set()
    for name in names:
        component = safe_component(name)
        key = component.casefold()
        if key not in seen:
            seen.add(key)
            clean.append(component)
    return clean[:12]


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


def suggested_memova_subdir(setup: dict[str, Any], existing_vault_path: Path) -> Path:
    hints = setup.get("target_path_hints") or {}
    name = None
    if isinstance(hints, dict):
        for key in ("memova_folder_name", "desired_memova_folder_name", "desired_vault_name", "vault_name"):
            value = hints.get(key)
            if isinstance(value, str) and value.strip():
                name = value
                break
    return resolved(existing_vault_path / safe_component(name or "Memova"))


def manifest_id(setup: dict[str, Any]) -> str:
    setup_id = setup.get("setup_session_id")
    if isinstance(setup_id, str) and setup_id:
        return f"memova-vault-{setup_id}"
    return "memova-vault-local"


def build_vault_mapping() -> dict[str, str]:
    return {
        "readme": "README.md",
        "agent_rules": "AGENTS.md",
        "sources": "sources",
        "inbox": "inbox",
        "wiki": "wiki",
        "schemas": "schemas",
        "projects": "projects",
        "daily": "daily",
        "outputs": "outputs",
        "archive": "archive",
        "_memova": "_memova",
    }


def build_file_specs(setup: dict[str, Any], *, now: str | None = None) -> list[FileSpec]:
    now = now or utc_now_iso()
    setup_mode = setup.get("setup_mode") or "create_new_vault"
    storage_target = setup.get("storage_target") or "icloud_drive"
    template_version = setup.get("vault_template_version") or TEMPLATE_VERSION
    preferences = setup.get("user_preferences") or {}
    confirmation_rules = (
        setup.get("vault_contract", {}).get("confirmation_rules")
        if isinstance(setup.get("vault_contract"), dict)
        else None
    ) or [
        "No memory without source.",
        "No action without evidence.",
        "No external write without confirmation.",
    ]

    manifest = {
        "schema_version": "memova_vault_manifest_v1",
        "manifest_id": manifest_id(setup),
        "created_at": now,
        "updated_at": now,
        "setup_session_id": setup.get("setup_session_id"),
        "workspace_id": setup.get("workspace_id"),
        "vault_template_version": template_version,
        "setup_package_schema_version": setup.get("schema_version") or SETUP_SCHEMA_VERSION,
        "setup_mode": setup_mode,
        "storage_target": storage_target,
        "semantic_roots": SEMANTIC_ROOTS,
        "confirmation_rules": confirmation_rules,
        "default_context_mode": "L2_compressed_project_memory",
    }

    specs = [
        FileSpec(
            "README.md",
            f"""# Memova Vault

This is a user-owned Memova knowledge base.

Memova captures meeting inputs, compiles evidence-backed briefs, proposes actions and memory
candidates, and syncs confirmed knowledge here as Markdown.

Core rules:

- No memory without source.
- No action without evidence.
- No external write without confirmation.

Primary roots:

- `sources/` stores raw evidence and imported material.
- `wiki/` stores confirmed long-term compiled knowledge.
- `projects/` stores project continuity and agent execution context.
- `_memova/` stores machine-readable manifest, mappings, indexes, and sync state.

Created by Memova setup on {now}.
""",
        ),
        FileSpec(
            "AGENTS.md",
            """# Agent Rules

These rules apply to Codex and other agents working inside this Memova Vault.

- Prefer Markdown files and filesystem-native links.
- Keep raw evidence in `sources/`; keep compiled knowledge in `wiki/`.
- Do not create long-term memory without source evidence.
- Do not create confirmed actions without evidence.
- Do not perform external writes without explicit user confirmation.
- Preserve user-authored files. Do not rename, relocate, or overwrite existing content unless the
  user explicitly approves that exact operation.
- Use `projects/*/_context/L2_project_summary.md` as default project context.
- Use `projects/*/_context/L3_following_context.md` only when the user enables deep following.
- Update `_memova/sync_state.json` through Memova-controlled sync operations, not by hand.
""",
        ),
        FileSpec(
            "sources/README.md",
            """# Sources

Raw evidence lives here: meeting source files, transcripts, captures, imports, attachments, and
source references. Agents may summarize sources, but should not rewrite them as if they were
confirmed long-term memory.
""",
        ),
        FileSpec(
            "inbox/README.md",
            """# Inbox

Low-friction holding area for captures, review queues, pending actions, pending memory candidates,
and conflicts that need user confirmation.
""",
        ),
        FileSpec(
            "inbox/review/pending_actions.md",
            """# Pending Actions

Unconfirmed action candidates waiting for user review.

Rules:

- No confirmed action without evidence.
- External writes require explicit user confirmation.
- Move confirmed project work into the relevant `projects/*/actions.md`.
""",
        ),
        FileSpec(
            "inbox/review/pending_memories.md",
            """# Pending Memories

Unconfirmed memory candidates waiting for user review.

Rules:

- No long-term memory without source evidence.
- Mark sensitive content before writing to long-term pages.
- Move confirmed knowledge into `wiki/` or `projects/` with source links.
""",
        ),
        FileSpec(
            "inbox/review/conflicts.md",
            """# Conflicts

Evidence conflicts and sync conflicts that need user or agent review.

Rules:

- Preserve both sides of a factual conflict until resolved.
- Do not silently overwrite user-authored content.
- Record resolution source and timestamp when a conflict is resolved.
""",
        ),
        FileSpec(
            "wiki/README.md",
            """# Wiki

Confirmed, source-linked, compiled knowledge. Every important claim should point back to evidence
in `sources/` or a Memova source id.
""",
        ),
        FileSpec(
            "projects/README.md",
            """# Projects

Project-level continuity for goals, decisions, open actions, risks, resources, and agent execution
context.
""",
        ),
        FileSpec(
            "daily/README.md",
            """# Daily

Optional daily planning and review notes.
""",
        ),
        FileSpec(
            "outputs/README.md",
            """# Outputs

Finished artifacts such as articles, reports, decks, product specs, and reusable deliverables.
""",
        ),
        FileSpec(
            "archive/README.md",
            """# Archive

Inactive but retained material. Archive content should not pollute active context by default.
""",
        ),
        FileSpec(
            "_memova/manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/vault_mapping.json",
            json.dumps(
                {
                    "schema_version": "memova_vault_mapping_v1",
                    "updated_at": now,
                    "setup_mode": setup_mode,
                    "semantic_roots": build_vault_mapping(),
                    "existing_structure_preserved": setup_mode
                    in {"connect_existing_vault", "add_memova_folder_to_existing_vault"},
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/links.json",
            json.dumps({"schema_version": "memova_links_v1", "updated_at": now, "links": []}, indent=2)
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/sync_state.json",
            json.dumps(
                {
                    "schema_version": "memova_sync_state_v1",
                    "updated_at": now,
                    "provider": storage_target,
                    "last_successful_sync_at": None,
                    "cursors": {},
                    "conflicts": [],
                },
                indent=2,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/wiki_index.json",
            json.dumps({"schema_version": "memova_wiki_index_v1", "updated_at": now, "pages": []}, indent=2)
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/source_index.json",
            json.dumps(
                {"schema_version": "memova_source_index_v1", "updated_at": now, "sources": []},
                indent=2,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/local_first_plan.md",
            f"""# Local-First Plan

Created: {now}

Current phase:

- Memova backend remains the operational source of truth for capture, processing, OAuth/MCP,
  actions, approvals, and sync state.
- This vault is the user-owned knowledge layer for confirmed, portable, agent-readable context.

Step-down path:

- Move confirmed personal knowledge into local Markdown first.
- Keep raw meeting evidence source-linked.
- Gradually replace cloud-backed display data with vault-backed reads when iOS sync is ready.
""",
            machine=True,
        ),
    ]

    for path, content in SCHEMA_FILES.items():
        specs.append(FileSpec(path, content))

    specs.extend(build_project_specs(extract_project_names(setup), now=now))

    if preferences:
        specs.append(
            FileSpec(
                "_memova/setup_preferences.json",
                json.dumps(
                    {
                        "schema_version": "memova_setup_preferences_v1",
                        "updated_at": now,
                        "preferences": preferences,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                machine=True,
            ),
        )

    return specs


def build_project_specs(project_names: list[str], *, now: str) -> list[FileSpec]:
    specs: list[FileSpec] = []
    for name in project_names:
        base = f"projects/Project - {name}"
        specs.extend(
            [
                FileSpec(
                    f"{base}/_project.md",
                    f"""# Project - {name}

type: project
status: active
created_at: {now}

## Goal

_Unconfirmed. Add the project goal after source-backed setup or user confirmation._

## People

- _Unconfirmed._

## Open Actions

- _None confirmed yet._

## Decisions

- _None confirmed yet._

## Risks

- _None confirmed yet._

## Sources

- _No sources linked yet._
""",
                ),
                FileSpec(
                    f"{base}/_context/L1_no_shared_memory.md",
                    "# L1 No Shared Memory\n\nUse only the current meeting/session evidence.\n",
                ),
                FileSpec(
                    f"{base}/_context/L2_project_summary.md",
                    "# L2 Project Summary\n\nDefault compressed project context. Keep this concise.\n",
                ),
                FileSpec(
                    f"{base}/_context/L3_following_context.md",
                    "# L3 Following Context\n\nDeep following context. Use only after explicit user opt-in.\n",
                ),
                FileSpec(f"{base}/actions.md", "# Actions\n\n"),
                FileSpec(f"{base}/decisions.md", "# Decisions\n\n"),
                FileSpec(f"{base}/meetings.md", "# Meetings\n\n"),
            ],
        )
    return specs


def build_dirs(setup: dict[str, Any]) -> list[str]:
    dirs = list(BASE_DIRS)
    for name in extract_project_names(setup):
        base = f"projects/Project - {name}"
        dirs.extend(
            [
                base,
                f"{base}/_context",
                f"{base}/outputs",
                f"{base}/resources",
            ],
        )
    return dirs


def create_plan(
    *,
    target_root: Path,
    setup: dict[str, Any],
    allow_non_icloud: bool = False,
    allow_existing_nonempty: bool = False,
    overwrite_machine_files: bool = False,
) -> dict[str, Any]:
    target_root = expand_path(str(target_root))
    setup_mode = setup.get("setup_mode") or "create_new_vault"
    storage_target = setup.get("storage_target") or "icloud_drive"
    exists = target_root.exists()
    nonempty = exists and any(target_root.iterdir())
    under_icloud = path_under_icloud(target_root)
    warnings: list[str] = []
    errors: list[str] = []

    if storage_target == "icloud_drive" and not under_icloud:
        message = "Target path is not under a detected iCloud Drive root."
        if allow_non_icloud:
            warnings.append(message)
        else:
            errors.append(message)
    if setup_mode == "create_new_vault" and nonempty and not allow_existing_nonempty:
        errors.append("Target root already exists and is not empty.")
    source_vault_paths = extract_source_vault_paths(setup)
    suggested_existing_vault_target = None
    if setup_mode == "add_memova_folder_to_existing_vault" and source_vault_paths:
        target_resolved = resolved(target_root)
        containing_sources = [source for source in source_vault_paths if path_inside(source, target_resolved)]
        if not containing_sources:
            errors.append(
                "For add_memova_folder_to_existing_vault, target root must be a dedicated Memova "
                "subdirectory inside the supplied existing vault path."
            )
            suggested_existing_vault_target = str(suggested_memova_subdir(setup, source_vault_paths[0]))
        else:
            exact_sources = [source for source in containing_sources if resolved(source) == target_resolved]
            if exact_sources:
                suggested_existing_vault_target = str(suggested_memova_subdir(setup, exact_sources[0]))
                errors.append(
                    "For add_memova_folder_to_existing_vault, target root cannot be the existing "
                    f"vault root itself. Use a dedicated Memova subdirectory such as "
                    f"{suggested_existing_vault_target}."
                )

    dirs = build_dirs(setup)
    files = build_file_specs(setup)
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

    return {
        "schema_version": "memova_vault_operation_plan_v1",
        "target_root": str(resolved(target_root)),
        "setup_mode": setup_mode,
        "storage_target": storage_target,
        "under_detected_icloud_root": under_icloud,
        "target_exists": exists,
        "target_nonempty": nonempty,
        "manifest_id": manifest_id(setup),
        "project_names": extract_project_names(setup),
        "source_vault_paths": [str(path) for path in source_vault_paths],
        "suggested_existing_vault_target": suggested_existing_vault_target,
        "warnings": warnings,
        "errors": errors,
        "operations": operations,
        "summary": summarize_operations(operations),
    }


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
    specs_by_path = {spec.path: spec for spec in build_file_specs(setup)}
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
        "manifest_id": plan["manifest_id"],
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
    missing_roots: list[str] = []
    for root_path in SEMANTIC_ROOTS:
        target = safe_join(root, root_path.rstrip("/"))
        if not target.exists():
            missing_roots.append(root_path)

    missing_machine_files: list[str] = []
    for relative_path in REQUIRED_MACHINE_FILES:
        if not safe_join(root, relative_path).is_file():
            missing_machine_files.append(relative_path)

    manifest_path = safe_join(root, "_memova/manifest.json")
    manifest: dict[str, Any] | None = None
    manifest_error: str | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            manifest_error = str(exc)

    status = "ok"
    if missing_roots or missing_machine_files or manifest_error:
        status = "fail"

    return {
        "schema_version": "memova_vault_validation_v1",
        "status": status,
        "path": str(resolved(root)),
        "missing_roots": missing_roots,
        "missing_machine_files": missing_machine_files,
        "manifest_id": manifest.get("manifest_id") if manifest else None,
        "manifest_error": manifest_error,
    }


def inspect_tree(path: Path, *, max_depth: int = 3, max_entries: int = 500) -> dict[str, Any]:
    root = expand_path(str(path))
    entries: list[dict[str, Any]] = []
    root_resolved = resolved(root)
    if not root.exists():
        return {
            "status": "not_found",
            "path": str(root_resolved),
            "entries": entries,
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

    semantic_presence = {
        root_path: safe_join(root, root_path.rstrip("/")).exists() for root_path in SEMANTIC_ROOTS
    }
    manifest_path = safe_join(root, "_memova/manifest.json")
    obsidian_path = root / ".obsidian"
    return {
        "status": "ok",
        "path": str(root_resolved),
        "entry_count": len(entries),
        "truncated": len(entries) >= max_entries,
        "has_memova_manifest": manifest_path.exists(),
        "has_obsidian_config": obsidian_path.exists(),
        "semantic_presence": semantic_presence,
        "entries": entries,
    }
