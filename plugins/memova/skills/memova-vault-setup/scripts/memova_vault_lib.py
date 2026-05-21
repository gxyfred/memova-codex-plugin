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
    "inbox/memova/",
    "sources/",
    "wiki/",
    "projects/",
    "daily/",
    "outputs/",
    "archive/",
    "schemas/",
    "_memova/",
]

INPUT_ROOT_REQUIRED_FILES = [
    "README.md",
    "AGENTS.md",
    "_memova/manifest.json",
    "_memova/input_root.json",
    "_memova/sync_state.json",
    "_memova/source_index.json",
]

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
    language = detect_language()
    zh = language == "zh"
    readme = (
        "# Memova 原始数据输入区\n\n"
        "这里保存 Memova 写入的会议原始数据和稳定处理结果。Memova V1 不负责整理你的 wiki、"
        "projects 或长期记忆；你可以让自己的工作流或 agent 从这里提取、压缩和分类。\n\n"
        "默认不保存音频文件，但会保存最终转写和 audio manifest。\n"
        if zh
        else "# Memova Raw Input Root\n\n"
        "This folder stores raw meeting data and stable processing outputs written by Memova. "
        "Memova V1 does not organize your wiki, projects, or long-term memory; your own workflows "
        "or agents can extract, compress, and classify from here.\n\n"
        "Audio files are not saved by default, but final transcripts and audio manifests are saved.\n"
    )
    agents = (
        "# Agent Rules\n\n"
        "- This folder is the Memova raw-input layer.\n"
        "- Do not treat files here as curated long-term knowledge.\n"
        "- Do not rewrite original transcripts, OCR text, attachments, or metadata.\n"
        "- Use these files as source material for user-approved extraction, compression, "
        "classification, wiki updates, and project updates.\n"
    )
    schemas = {
        "schemas/meeting_packet.schema.md": "# Meeting Packet Schema\n\nRequired files: metadata.json, transcript.md, final_note.md, hashes.json.\n",
        "schemas/transcript.schema.md": "# Transcript Schema\n\nFinal transcript files should be stable source outputs, not realtime drafts.\n",
        "schemas/note.schema.md": "# Note Schema\n\nFinal note and raw user note files belong to the same meeting packet.\n",
        "schemas/ocr.schema.md": "# OCR Schema\n\nStore OCR text, page text, source image references, and page metadata.\n",
        "schemas/attachment.schema.md": "# Attachment Schema\n\nStore attachment files and attachment metadata when available.\n",
    }
    files = [
        FileSpec("README.md", readme),
        FileSpec("AGENTS.md", agents),
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
    files.extend(FileSpec(path, content) for path, content in schemas.items())
    if prefix:
        return [FileSpec(f"{prefix}/{spec.path}", spec.content, spec.machine) for spec in files]
    return files


def root_file_specs(setup: dict[str, Any], *, now: str) -> list[FileSpec]:
    return [
        FileSpec(
            "README.md",
            f"""# Memova Vault

This is a user-owned Memova knowledge base.

Memova V1 writes complete meeting raw-input packets only under `inbox/memova/`.
Other roots such as `sources/`, `wiki/`, `projects/`, `daily/`, and `outputs/` are empty surfaces
for the user or future agent workflows.

Created by Memova setup on {now}.
""",
        ),
        FileSpec(
            "AGENTS.md",
            """# Agent Rules

- Treat `inbox/memova/` as the Memova raw-input layer.
- Do not treat Memova input packets as curated long-term knowledge.
- Do not reorganize user-authored folders without explicit user approval.
- Use Memova input packets as source material for user-approved extraction and classification.
""",
        ),
        FileSpec(
            "inbox/README.md",
            "# Inbox\n\nLow-friction input area. Memova writes raw meeting packets under `memova/`.\n",
        ),
        FileSpec("sources/README.md", "# Sources\n\nReserved for user or future agent workflows.\n"),
        FileSpec("wiki/README.md", "# Wiki\n\nReserved for curated long-term knowledge.\n"),
        FileSpec("projects/README.md", "# Projects\n\nReserved for project organization.\n"),
        FileSpec("daily/README.md", "# Daily\n\nReserved for daily notes.\n"),
        FileSpec("outputs/README.md", "# Outputs\n\nReserved for finished artifacts.\n"),
        FileSpec("archive/README.md", "# Archive\n\nReserved for inactive material.\n"),
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
    return {
        "schema_version": "memova_vault_operation_plan_v1",
        "target_root": str(resolved(target_root)),
        "setup_mode": mode,
        "storage_target": storage_target,
        "vault_template_version": setup.get("vault_template_version") or TEMPLATE_VERSION,
        "target_kind": "memova_input_root" if mode == "connect_existing_vault" else "memova_vault",
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
    input_root = safe_join(root, INPUT_ROOT_RELATIVE_PATH) if is_new_vault else root

    if is_new_vault:
        for root_path in NEW_VAULT_REQUIRED_ROOTS:
            target = safe_join(root, root_path.rstrip("/"))
            if not target.exists():
                missing_roots.append(root_path)
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

    manifest_path = safe_join(input_root, "_memova/manifest.json")
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
        "target_kind": "memova_vault" if is_new_vault else "memova_input_root",
        "memova_input_root_path": str(resolved(input_root)),
        "memova_input_root_relative_path": INPUT_ROOT_RELATIVE_PATH
        if is_new_vault
        else manifest.get("memova_input_root_relative_path", ".")
        if manifest
        else ".",
        "missing_roots": missing_roots,
        "missing_machine_files": missing_machine_files,
        "vault_manifest_id": manifest_id_from_root(root) if is_new_vault else None,
        "input_root_manifest_id": manifest.get("manifest_id") if manifest else None,
        "manifest_id": manifest.get("manifest_id") if manifest else None,
        "manifest_error": manifest_error,
    }


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
