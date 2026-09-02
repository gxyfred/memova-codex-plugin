from __future__ import annotations

import json
import os
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

V2_TEMPLATE_VERSION = "memova_knowledge_base_v2"
V3_TEMPLATE_VERSION = "memova_knowledge_base_v3"
V4_TEMPLATE_VERSION = "memova_knowledge_base_v4"
BACKEND_TEMPLATE_VERSIONS = {V3_TEMPLATE_VERSION, V4_TEMPLATE_VERSION}
SUPPORTED_TEMPLATE_VERSIONS = {V2_TEMPLATE_VERSION, *BACKEND_TEMPLATE_VERSIONS}
TEMPLATE_VERSION = V2_TEMPLATE_VERSION
SETUP_SCHEMA_VERSION = "knowledge_base_setup_v1"
VALIDATION_RESULT_SCHEMA_VERSION = "memova_kb_v2_validation_result_v1"
REPAIR_PACKAGE_SCHEMA_VERSION = "memova_kb_v2_repair_package_v1"
V3_VALIDATION_RESULT_SCHEMA_VERSION = "memova_kb_v3_validation_result_v1"
V3_REPAIR_PACKAGE_SCHEMA_VERSION = "memova_kb_v3_repair_package_v1"
V4_VALIDATION_RESULT_SCHEMA_VERSION = "memova_kb_v4_validation_result_v1"
V4_REPAIR_PACKAGE_SCHEMA_VERSION = "memova_kb_v4_repair_package_v1"
INPUT_ROOT_RELATIVE_PATH = "."
INPUT_ROOT_FOLDER_NAME = "Memova"
DEFAULT_NEW_VAULT_FOLDER_NAME = "Memova Vault"
ALLOWED_SETUP_MODES = {"create_new_vault", "connect_existing_vault"}
ALLOWED_WRITE_MODES = {"create", "replace", "replace_machine_file", "skip_if_exists"}

NEW_VAULT_DIRS = [
    "inbox/meetings",
    "inbox/captures",
    "inbox/imports",
    "inbox/activity",
    "wiki/people",
    "wiki/organizations",
    "wiki/topics",
    "wiki/decisions",
    "wiki/processes",
    "wiki/references",
    "projects",
    "daily",
    "outputs/reports",
    "outputs/briefs",
    "outputs/specs",
    "outputs/decks",
    "outputs/assets",
    "archive",
    "schemas",
    "_memova",
]

INPUT_ROOT_DIRS = [
    *NEW_VAULT_DIRS,
]

NEW_VAULT_REQUIRED_ROOTS = [
    "index.md",
    "README.md",
    "AGENTS.md",
    "log.md",
    "inbox/",
    "inbox/README.md",
    "inbox/index.md",
    "wiki/",
    "wiki/index.md",
    "wiki/people/index.md",
    "wiki/organizations/index.md",
    "wiki/topics/index.md",
    "wiki/decisions/index.md",
    "wiki/processes/index.md",
    "wiki/references/index.md",
    "projects/",
    "projects/index.md",
    "daily/",
    "daily/index.md",
    "outputs/",
    "outputs/index.md",
    "archive/",
    "archive/index.md",
    "schemas/",
    "schemas/index.md",
    "schemas/README.md",
    "_memova/",
]

INPUT_ROOT_REQUIRED_FILES = [
    "index.md",
    "README.md",
    "AGENTS.md",
    "log.md",
    "inbox/index.md",
    "inbox/README.md",
    "wiki/index.md",
    "wiki/people/index.md",
    "wiki/organizations/index.md",
    "wiki/topics/index.md",
    "wiki/decisions/index.md",
    "wiki/processes/index.md",
    "wiki/references/index.md",
    "projects/index.md",
    "daily/index.md",
    "outputs/index.md",
    "schemas/index.md",
    "schemas/README.md",
    "schemas/okf-concept.schema.md",
    "schemas/memova-root.schema.md",
    "schemas/meeting-packet.schema.md",
    "schemas/capture-packet.schema.md",
    "schemas/import-packet.schema.md",
    "schemas/activity-event.schema.md",
    "schemas/promotion.schema.md",
    "schemas/project.schema.md",
    "schemas/daily.schema.md",
    "schemas/output.schema.md",
    "schemas/citation.schema.md",
    "archive/index.md",
    "_memova/manifest.json",
    "_memova/root.json",
    "_memova/tree_manifest.json",
    "_memova/sync_state.json",
    "_memova/source_index.json",
    "_memova/promotion_index.json",
    "_memova/repair_state.json",
]

SETUP_IDENTITY_FILE_PATHS = {
    "_memova/manifest.json",
}

MACHINE_JSON_SCHEMA_VERSIONS = {
    "_memova/manifest.json": "memova_root_manifest_v2",
    "_memova/root.json": "memova_root_v2",
    "_memova/tree_manifest.json": "memova_tree_manifest_v1",
    "_memova/sync_state.json": "memova_root_sync_state_v1",
    "_memova/source_index.json": "memova_source_index_v1",
    "_memova/promotion_index.json": "memova_promotion_index_v1",
    "_memova/repair_state.json": "memova_repair_state_v1",
}

V3_MACHINE_JSON_SCHEMA_VERSIONS = {
    "_memova/manifest.json": "memova_root_manifest_v3",
    "_memova/root.json": "memova_root_v3",
    "_memova/tree_manifest.json": "memova_tree_manifest_v2",
    "_memova/cloud_state.json": "memova_cloud_state_v1",
    "_memova/source_index.json": "memova_source_index_v1",
    "_memova/sync_state.json": "memova_root_sync_state_v1",
    "_memova/promotion_index.json": "memova_promotion_index_v1",
    "_memova/graph_index.json": "memova_graph_index_v1",
    "_memova/repair_state.json": "memova_repair_state_v1",
}

NEW_VAULT_DOC_CHECKS = {
    "index.md": ["Memova Knowledge Base", "inbox", "wiki"],
    "README.md": ["Memova Knowledge Base", "V2", "inbox/"],
    "AGENTS.md": ["No memory without source", "No external write without confirmation"],
    "inbox/README.md": ["Inbox", "inbox/meetings"],
    "wiki/index.md": ["Wiki", "source citation"],
    "projects/index.md": ["Projects", "action projection"],
    "daily/index.md": ["Daily", "digest"],
    "outputs/index.md": ["Outputs", "reports"],
    "archive/index.md": ["Archive", "inactive"],
    "schemas/README.md": ["Schemas", "OKF"],
}

INPUT_ROOT_DOC_CHECKS = {
    **NEW_VAULT_DOC_CHECKS,
    "README.md": [
        "Memova Knowledge Base",
        "V2",
        "inbox/",
        "sources.md",
        "promotion.json",
    ],
    "AGENTS.md": [
        "Agent Rules",
        "No memory without source",
        "No action without evidence",
        "inbox/",
    ],
    "schemas/meeting-packet.schema.md": [
        "Meeting Packet Schema",
        "sources.md",
        "note.md",
        "promotion.json",
    ],
    "schemas/promotion.schema.md": [
        "Promotion Schema",
        "promotion_status",
        "promotion_index",
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
    role: str | None = None
    content_type: str = "text/markdown"
    write_mode: str = "skip_if_exists"
    sha256: str | None = None
    byte_size: int | None = None
    memova_uri: str | None = None
    expected_existing_sha256: str | None = None
    preserve_if_modified: bool = True


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
    template_version = setup_template_version(setup)
    if template_version not in SUPPORTED_TEMPLATE_VERSIONS:
        errors.append(
            "vault_template_version must be memova_knowledge_base_v2, "
            "memova_knowledge_base_v3, or memova_knowledge_base_v4"
        )
        return errors
    contract = setup.get("vault_contract")
    if isinstance(contract, dict):
        contract_template = contract.get("template")
        if contract_template and contract_template != template_version:
            errors.append("vault_contract.template must match vault_template_version")
    if template_version in BACKEND_TEMPLATE_VERSIONS:
        errors.extend(backend_setup_operation_errors(setup))
    return errors


def setup_template_version(setup: dict[str, Any]) -> str:
    return str(setup.get("vault_template_version") or V2_TEMPLATE_VERSION)


def setup_operations(setup: dict[str, Any]) -> dict[str, Any] | None:
    contract = setup.get("vault_contract")
    if not isinstance(contract, dict):
        return None
    managed_root = contract.get("memova_managed_root")
    if not isinstance(managed_root, dict):
        return None
    operations = managed_root.get("setup_operations")
    return operations if isinstance(operations, dict) else None


def strict_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("\\", "/").strip("/")
    if (
        not normalized
        or normalized == "."
        or value.startswith(("/", "\\", "~"))
        or ":" in normalized
        or "\x00" in normalized
    ):
        return None
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return "/".join(parts)


def backend_setup_operation_errors(setup: dict[str, Any]) -> list[str]:
    operations = setup_operations(setup)
    if operations is None:
        return [
            "Backend-owned setup package must include "
            "vault_contract.memova_managed_root.setup_operations"
        ]
    directories = operations.get("directories")
    files = operations.get("files")
    errors: list[str] = []
    if not isinstance(directories, list):
        errors.append("Backend setup_operations.directories must be an array")
        directories = []
    if not isinstance(files, list):
        errors.append("Backend setup_operations.files must be an array")
        files = []
    if not directories:
        errors.append("Backend setup_operations.directories must not be empty")
    if not files:
        errors.append("Backend setup_operations.files must not be empty")

    seen_paths: set[str] = set()
    for index, item in enumerate(directories):
        prefix = f"Backend directory operation {index}"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        relative_path = strict_relative_path(item.get("relative_path"))
        if relative_path is None:
            errors.append(f"{prefix} has an unsafe relative_path")
        elif relative_path in seen_paths:
            errors.append(f"duplicate backend operation path: {relative_path}")
        else:
            seen_paths.add(relative_path)
        if item.get("write_mode", "create") != "create":
            errors.append(f"{prefix} write_mode must be create")

    for index, item in enumerate(files):
        prefix = f"Backend file operation {index}"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        relative_path = strict_relative_path(item.get("relative_path"))
        if relative_path is None:
            errors.append(f"{prefix} has an unsafe relative_path")
        elif relative_path in seen_paths:
            errors.append(f"duplicate backend operation path: {relative_path}")
        else:
            seen_paths.add(relative_path)
        if str(item.get("encoding", "utf-8")).lower() != "utf-8":
            errors.append(f"{prefix} must use utf-8 encoding")
        if item.get("write_mode") not in ALLOWED_WRITE_MODES:
            errors.append(f"{prefix} has an unsupported write_mode")
        content = item.get("content")
        if not isinstance(content, str):
            errors.append(f"{prefix} content must be a string")
            continue
        content_bytes = content.encode("utf-8")
        expected_sha256 = hashlib.sha256(content_bytes).hexdigest()
        if item.get("sha256") != expected_sha256:
            errors.append(f"{prefix} sha256 does not match content")
        if item.get("byte_size") != len(content_bytes):
            errors.append(f"{prefix} byte_size does not match content")
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
    backend_manifest = backend_manifest_content(setup)
    if backend_manifest and isinstance(backend_manifest.get("manifest_id"), str):
        return str(backend_manifest["manifest_id"])
    setup_id = setup.get("setup_session_id")
    if isinstance(setup_id, str) and setup_id:
        return f"memova-vault-{setup_id}"
    return "memova-vault-local"


def input_root_manifest_id(setup: dict[str, Any]) -> str:
    backend_manifest = backend_manifest_content(setup)
    if backend_manifest and isinstance(backend_manifest.get("input_root_manifest_id"), str):
        return str(backend_manifest["input_root_manifest_id"])
    setup_id = setup.get("setup_session_id")
    if isinstance(setup_id, str) and setup_id:
        return f"memova-input-root-{setup_id}"
    return "memova-input-root-local"


def is_setup_identity_file(relative_path: str) -> bool:
    normalized = relative_path.strip().replace("\\", "/")
    return normalized in SETUP_IDENTITY_FILE_PATHS


def backend_manifest_content(setup: dict[str, Any]) -> dict[str, Any] | None:
    if setup_template_version(setup) not in BACKEND_TEMPLATE_VERSIONS:
        return None
    operations = setup_operations(setup) or {}
    for item in operations.get("files") or []:
        if not isinstance(item, dict) or item.get("relative_path") != "_memova/manifest.json":
            continue
        content = item.get("content")
        if not isinstance(content, str):
            return None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


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
    folder_name = input_root_folder_name(setup)
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
        "schema_version": "memova_root_manifest_v2",
        "manifest_id": manifest_id(setup),
        "input_root_manifest_id": input_root_manifest_id(setup),
        "created_at": now,
        "updated_at": now,
        "setup_session_id": setup.get("setup_session_id"),
        "workspace_id": setup.get("workspace_id"),
        "vault_template_version": setup.get("vault_template_version") or TEMPLATE_VERSION,
        "setup_package_schema_version": setup.get("schema_version") or SETUP_SCHEMA_VERSION,
        "setup_mode": setup_mode(setup),
        "storage_target": setup.get("storage_target") or "icloud_drive",
        "memova_input_root_relative_path": INPUT_ROOT_RELATIVE_PATH,
        "ownership_scope": "memova_managed_root_v2",
        "semantic_roots": {
            "inbox": "inbox",
            "wiki": "wiki",
            "projects": "projects",
            "daily": "daily",
            "outputs": "outputs",
            "schemas": "schemas",
            "archive": "archive",
            "_memova": "_memova",
        },
    }


def input_root_manifest(
    setup: dict[str, Any],
    *,
    now: str,
    relative_path: str,
) -> dict[str, Any]:
    manifest = root_manifest(setup, now=now)
    manifest["memova_input_root_relative_path"] = relative_path
    return manifest


def input_root_file_specs(
    setup: dict[str, Any],
    *,
    now: str,
    relative_path: str,
    prefix: str = "",
) -> list[FileSpec]:
    schema_specs = input_root_schema_specs()
    files = [
        FileSpec("index.md", root_index(), machine=True),
        FileSpec("README.md", input_root_readme(relative_path=relative_path), machine=True),
        FileSpec("AGENTS.md", input_root_agents(relative_path=relative_path), machine=True),
        FileSpec("log.md", markdown("# Log\n\n- Memova Knowledge Base V2 setup initialized."), machine=True),
        FileSpec("inbox/index.md", area_index("Inbox", "原始输入和 staging 层。", ["meetings", "captures", "imports", "activity"]), machine=True),
        FileSpec(
            "inbox/README.md",
            markdown(
                """# Inbox

Inbox 是 Memova 的 source-first 输入层。会议 packet 写入
`inbox/meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/`，轻量捕捉写入
`inbox/captures/`，外部导入写入 `inbox/imports/`，用户动作和产品事件写入
`inbox/activity/`。

这里的内容可以灵活变化，但需要保留 source packet、manifest、sources.md、
packet.json 和 promotion.json，方便后续整理流程把原始输入提升到 wiki、projects、
daily 或 outputs。Inbox 不是长期事实层；长期结论必须在整理后带来源引用。
"""
            ),
            machine=True,
        ),
        FileSpec("wiki/index.md", area_index("Wiki", "长期、可复用、带 source citation 的 OKF-compatible 知识概念。", ["people", "organizations", "topics", "decisions", "processes", "references"]), machine=True),
        FileSpec("wiki/people/index.md", area_index("People", "人物相关长期知识。", []), machine=True),
        FileSpec("wiki/organizations/index.md", area_index("Organizations", "组织相关长期知识。", []), machine=True),
        FileSpec("wiki/topics/index.md", area_index("Topics", "可复用主题知识。", []), machine=True),
        FileSpec("wiki/decisions/index.md", area_index("Decisions", "已确认决策和决策理由。", []), machine=True),
        FileSpec("wiki/processes/index.md", area_index("Processes", "可重复流程和 runbook。", []), machine=True),
        FileSpec("wiki/references/index.md", area_index("References", "整理后的参考资料索引。", []), machine=True),
        FileSpec("projects/index.md", area_index("Projects", "项目级上下文、决策、action projection 和输出索引。", []), machine=True),
        FileSpec("daily/index.md", area_index("Daily", "日期维度 digest、计划和复盘。", []), machine=True),
        FileSpec("outputs/index.md", area_index("Outputs", "reports、briefs、specs、decks 和 assets。", ["reports", "briefs", "specs", "decks", "assets"]), machine=True),
        FileSpec("schemas/index.md", area_index("Schemas", "Memova V2 文件树与 OKF schema 约定。", []), machine=True),
        FileSpec(
            "schemas/README.md",
            markdown(
                """# Schemas

Schemas 目录保存 Memova V2 文件树、OKF-compatible 文档、meeting packet、
capture packet、import packet、activity event、promotion、citation 和 output 的约定。

这些 Markdown schema 是给人和 agent 读取的稳定契约；真正的运行时状态仍以
`_memova/manifest.json`、`_memova/root.json`、`_memova/tree_manifest.json`、
`_memova/source_index.json` 和 `_memova/promotion_index.json` 为准。
"""
            ),
            machine=True,
        ),
        FileSpec("archive/index.md", area_index("Archive", "inactive 或被替代但仍需保留的内容。", []), machine=True),
        FileSpec(
            "_memova/manifest.json",
            json.dumps(input_root_manifest(setup, now=now, relative_path=relative_path), indent=2, ensure_ascii=False)
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/root.json",
            json.dumps(
                {
                    "schema_version": "memova_root_v2",
                    "updated_at": now,
                    "relative_path": relative_path,
                    "packet_roots": {
                        "meeting": "inbox/meetings",
                        "capture": "inbox/captures",
                        "import": "inbox/imports",
                        "activity": "inbox/activity",
                    },
                    "path_policies": {
                        "meeting_packet": {
                            "version": "date_sharded_v1",
                            "template": "YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id_short>",
                        },
                        "activity_event": {
                            "version": "date_sharded_v1",
                            "template": "YYYY/MM/YYYY-MM-DD-<event_type>-<event_id_short>",
                        },
                    },
                    "okf_compatible_roots": ["wiki", "projects", "daily", "outputs", "schemas"],
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
            "_memova/tree_manifest.json",
            json.dumps(
                {
                    "schema_version": "memova_tree_manifest_v1",
                    "updated_at": now,
                    "required_directories": sorted(NEW_VAULT_DIRS),
                    "required_files": INPUT_ROOT_REQUIRED_FILES,
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
                    "schema_version": "memova_root_sync_state_v1",
                    "updated_at": now,
                    "last_successful_sync_at": None,
                    "conflicts": [],
                    "cloud_mirror": {"enabled": False, "last_revision": None},
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
                    "schema_version": "memova_source_index_v1",
                    "updated_at": now,
                    "meetings": [],
                    "captures": [],
                    "imports": [],
                    "activity": [],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/promotion_index.json",
            json.dumps(
                {
                    "schema_version": "memova_promotion_index_v1",
                    "updated_at": now,
                    "promotions": [],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
        FileSpec(
            "_memova/repair_state.json",
            json.dumps(
                {
                    "schema_version": "memova_repair_state_v1",
                    "updated_at": now,
                    "status": "ok",
                    "issues": [],
                    "last_validation": None,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            machine=True,
        ),
    ]
    files.extend(FileSpec(path, content, machine=True) for path, content in schema_specs.items())
    if prefix:
        return [FileSpec(f"{prefix}/{spec.path}", spec.content, spec.machine) for spec in files]
    return files


def input_root_readme(*, relative_path: str) -> str:
    return markdown(
        f"""# Memova Knowledge Base

This folder is the Memova-managed Knowledge Base V2 root. Its relative path in the selected vault is
`{relative_path}`.

Memova writes source evidence into `inbox/` first, then later promotion workflows can write durable,
source-cited knowledge into `wiki/`, `projects/`, `daily/`, or `outputs/`.

## What Memova Writes

Meeting packets are written under `inbox/meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/`.
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

- Memova does not save audio files by default. Audio provenance is recorded in `packet.json` and
  `assets/manifest.json` when relevant.
- Memova does not turn meeting content into long-term memory without source references and a later
  user-confirmed extraction workflow.

## How Agents Should Use This Folder

Use this folder as evidence, not as truth after interpretation. When an agent creates wiki pages,
project updates, action lists, or summaries from these packets, it should cite the packet path and
the specific source section or JSON pointer it used. Keep packet source files stable so future
compilers can re-run from the same evidence.

See `index.md` for the root index, `AGENTS.md` for operating rules, and `schemas/*.schema.md` for
the file contracts. `promotion.json` remains the packet-level promotion state for meeting packets.
"""
    )


def input_root_agents(*, relative_path: str) -> str:
    return markdown(
        f"""# Agent Rules For Memova Knowledge Base

Scope: this file applies to the Memova managed root at `{relative_path}`.

## Core Rules

- Treat `inbox/` as source evidence and staging, not curated long-term knowledge.
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
  `inbox/meetings/2026/05/2026-05-21-example-meeting-<meeting_id>/sources.md#transcript`;
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


def root_index() -> str:
    return markdown(
        """---
type: Index
title: Memova Knowledge Base
description: Memova V2 managed knowledge-base root.
tags: [memova, knowledge-base]
memova:
  schema_version: memova_okf_extension_v1
  status: active
---

# Memova Knowledge Base

This is the OKF-compatible Memova Knowledge Base V2 root.

## Areas

- `inbox/`: source packets, captures, imports, and activity events.
- `wiki/`: reusable source-cited long-term knowledge.
- `projects/`: project context, decisions, action projection, and output index.
- `daily/`: date-based digest.
- `outputs/`: reports, briefs, specs, decks, and assets.
- `schemas/`: human and agent-readable schema notes.
"""
    )


def area_index(title: str, description: str, children: list[str]) -> str:
    child_lines = "\n".join(f"- `{child}/`" for child in children) if children else "- No pages yet."
    return markdown(
        f"""---
type: Index
title: {title}
description: {description}
tags: [memova]
memova:
  schema_version: memova_okf_extension_v1
  status: active
---

# {title}

{description}

This index is part of the Memova Knowledge Base V2 managed root. Keep it lightweight and use it as a
navigation surface rather than a place for uncited facts. When pages are added here, they should either
point back to an inbox source packet or clearly state that the content is still a draft awaiting
promotion.

## Children

{child_lines}
"""
    )


def input_root_index() -> str:
    return markdown(
        """# Memova Inbox Index

This index is the stable entry point for Memova meeting packets.

Meeting packets live under:

```text
inbox/meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/
```

## recent meeting packets

Memova and iOS may append lightweight links here in a later version. For now, use the date-partitioned
`inbox/meetings/` folder and each packet's `manifest.json` to discover synced meetings.

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
        "schemas/okf-concept.schema.md": markdown("# OKF Concept Schema\n\nOKF-compatible pages use YAML frontmatter with `type`, `title`, `description`, tags, links, Related, and Citations."),
        "schemas/memova-root.schema.md": markdown("# Memova Root Schema\n\n`Memova/` is the V2 managed root. `_memova/manifest.json`, `root.json`, and `tree_manifest.json` define identity and path policy."),
        "schemas/meeting-packet.schema.md": meeting_packet_schema(),
        "schemas/capture-packet.schema.md": markdown("# Capture Packet Schema\n\nCapture packets live under `inbox/captures/`."),
        "schemas/import-packet.schema.md": markdown("# Import Packet Schema\n\nImport packets live under `inbox/imports/` and preserve original files before digest/promotion."),
        "schemas/activity-event.schema.md": markdown("# Activity Event Schema\n\nActivity events live under `inbox/activity/` and capture user edits or product actions."),
        "schemas/promotion.schema.md": promotion_schema(),
        "schemas/project.schema.md": markdown("# Project Schema\n\nProject pages keep context, decisions, action projection, outputs, and log files."),
        "schemas/daily.schema.md": markdown("# Daily Schema\n\nDaily pages are date-based digests, not the source of long-term project/wiki truth."),
        "schemas/output.schema.md": markdown("# Output Schema\n\nOutputs include reports, briefs, specs, decks, and asset index pages."),
        "schemas/citation.schema.md": markdown("# Citation Schema\n\nImportant claims must cite source packets with `memova.source_refs` or `# Citations`."),
    }


def meeting_packet_schema() -> str:
    return markdown(
        """# Meeting Packet Schema

This schema describes one Memova meeting packet under:

```text
inbox/meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/
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
wiki/project/action/memory surfaces. `_memova/promotion_index.json` is the root-level promotion_index
used for quick discovery across packets and downstream targets.

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


def build_dirs(setup: dict[str, Any]) -> list[str]:
    if setup_template_version(setup) in BACKEND_TEMPLATE_VERSIONS:
        operations = setup_operations(setup) or {}
        return [
            str(item["relative_path"])
            for item in operations.get("directories") or []
            if isinstance(item, dict) and strict_relative_path(item.get("relative_path"))
        ]
    return list(NEW_VAULT_DIRS)


def build_file_specs(setup: dict[str, Any], *, target_root: Path, now: str | None = None) -> list[FileSpec]:
    if setup_template_version(setup) in BACKEND_TEMPLATE_VERSIONS:
        operations = setup_operations(setup) or {}
        specs: list[FileSpec] = []
        for item in operations.get("files") or []:
            if not isinstance(item, dict):
                continue
            relative_path = strict_relative_path(item.get("relative_path"))
            content = item.get("content")
            if relative_path is None or not isinstance(content, str):
                continue
            specs.append(
                FileSpec(
                    path=relative_path,
                    content=content,
                    machine=bool(item.get("machine_managed", True)),
                    role=str(item.get("role") or "memova_v3_setup_file"),
                    content_type=str(item.get("content_type") or "text/markdown"),
                    write_mode=str(item.get("write_mode") or "skip_if_exists"),
                    sha256=str(item.get("sha256") or hashlib.sha256(content.encode("utf-8")).hexdigest()),
                    byte_size=int(item.get("byte_size") or len(content.encode("utf-8"))),
                    memova_uri=str(item["memova_uri"]) if item.get("memova_uri") else None,
                    expected_existing_sha256=(
                        str(item["expected_existing_sha256"])
                        if item.get("expected_existing_sha256")
                        else None
                    ),
                    preserve_if_modified=bool(item.get("preserve_if_modified", True)),
                )
            )
        return specs
    now = now or utc_now_iso()
    relative_path = memova_input_root_relative_path(setup, target_root)
    return input_root_file_specs(setup, now=now, relative_path=relative_path)


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
    package_errors = setup_package_errors(setup)
    errors: list[str] = list(package_errors)
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
        # iCloud discovery is macOS-specific and can legitimately return no existing root on
        # Windows/Linux or a fresh Mac. Planning still knows the user-selected parent directory,
        # so provide a deterministic sibling suggestion instead of dropping the recovery target.
        suggested = suggested_new_vault_target(setup) or target_root.parent / desired_folder
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
                "For connect_existing_vault, target root must be the root-level Memova managed "
                "sub-knowledge-base folder inside the supplied existing vault path."
            )
        else:
            exact_sources = [source for source in containing_sources if resolved(source) == target_resolved]
            if exact_sources:
                suggested_existing_vault_target = str(
                    suggested_existing_input_target(setup, exact_sources[0]),
                )
                errors.append(
                    "For connect_existing_vault, target root cannot be the existing vault root "
                    f"itself. Use the root-level Memova managed folder such as "
                    f"{suggested_existing_vault_target}."
                )

    dirs = [] if package_errors else build_dirs(setup)
    files = [] if package_errors else build_file_specs(setup, target_root=target_root)
    operations: list[dict[str, Any]] = []
    for directory in dirs:
        path = safe_join(target_root, directory)
        if path.exists() and not path.is_dir():
            errors.append(f"Required directory path is occupied by a non-directory item: {directory}")
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
        if exists_file and not path.is_file():
            errors.append(f"Required file path is occupied by a non-file item: {spec.path}")
        status, current_sha256 = planned_file_status(
            path,
            spec,
            overwrite_machine_files=overwrite_machine_files,
        )
        if status == "preserve_modified":
            warnings.append(
                f"Preserving locally modified file because its hash differs from the backend expectation: {spec.path}"
            )
        operations.append(
            {
                "op": "write_file",
                "path": str(path),
                "relative_path": spec.path,
                "status": status,
                "machine_file": spec.machine,
                "bytes": len(spec.content.encode("utf-8")),
                "sha256": spec.sha256 or hashlib.sha256(spec.content.encode("utf-8")).hexdigest(),
                "write_mode": spec.write_mode,
                "preserve_if_modified": spec.preserve_if_modified,
                "expected_existing_sha256": spec.expected_existing_sha256,
                "current_sha256": current_sha256,
            },
        )

    relative_path = memova_input_root_relative_path(setup, target_root)
    target_kind = "memova_managed_root" if mode == "connect_existing_vault" else "memova_vault"
    plan_target_root = str(resolved(target_root))
    plan = {
        "schema_version": "memova_vault_operation_plan_v1",
        "target_root": plan_target_root,
        "setup_mode": mode,
        "storage_target": storage_target,
        "vault_template_version": setup_template_version(setup),
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


def planned_file_status(
    path: Path,
    spec: FileSpec,
    *,
    overwrite_machine_files: bool,
) -> tuple[str, str | None]:
    if not path.exists() or not path.is_file():
        return "create", None
    current_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if spec.write_mode == "replace_machine_file" and spec.machine:
        return "overwrite", current_sha256
    if (
        spec.preserve_if_modified
        and spec.expected_existing_sha256
        and current_sha256 != spec.expected_existing_sha256
    ):
        return "preserve_modified", current_sha256
    if setup_spec_replaces_existing(spec, overwrite_machine_files=overwrite_machine_files):
        return "overwrite", current_sha256
    return "skip", current_sha256


def setup_spec_replaces_existing(spec: FileSpec, *, overwrite_machine_files: bool) -> bool:
    if spec.write_mode == "replace":
        return True
    if spec.write_mode == "replace_machine_file" and spec.machine:
        return True
    return bool(
        spec.machine
        and (overwrite_machine_files or is_setup_identity_file(spec.path))
    )


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
    written_files: list[dict[str, Any]] = []

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
        if operation.get("status") in {"skip", "preserve_modified"}:
            skipped_files.append(operation["relative_path"])
            continue
        path.write_text(spec.content, encoding="utf-8")
        written_files.append(
            {
                "relative_path": operation["relative_path"],
                "sha256": hashlib.sha256(spec.content.encode("utf-8")).hexdigest(),
                "byte_size": len(spec.content.encode("utf-8")),
            }
        )
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
        "written_files": written_files,
        "identity_validation": setup_identity_validation(target_root, setup),
    }


def validate_vault(path: Path, setup: dict[str, Any] | None = None) -> dict[str, Any]:
    root = expand_path(str(path))
    manifest, _manifest_error = read_json_file(safe_join(root, "_memova/manifest.json"))
    detected_template = (manifest or {}).get("vault_template_version")
    requested_template = setup_template_version(setup) if setup else None
    template_version = requested_template or detected_template or V2_TEMPLATE_VERSION
    if template_version in BACKEND_TEMPLATE_VERSIONS:
        return validate_v3_vault(root, setup=setup, template_version=template_version)
    return validate_v2_vault(root)


def validate_v3_vault(
    path: Path,
    setup: dict[str, Any] | None = None,
    template_version: str | None = None,
) -> dict[str, Any]:
    root = expand_path(str(path))
    manifest_path = safe_join(root, "_memova/manifest.json")
    manifest, manifest_error = read_json_file(manifest_path)
    template_version = (
        template_version
        or (setup_template_version(setup) if setup else None)
        or (manifest or {}).get("vault_template_version")
        or V3_TEMPLATE_VERSION
    )
    tree_manifest, tree_manifest_error = read_json_file(safe_join(root, "_memova/tree_manifest.json"))
    issues: list[dict[str, Any]] = []
    missing_directories: list[str] = []
    missing_files: list[str] = []
    blocked_directories: list[str] = []
    blocked_files: list[str] = []
    machine_json_issues: list[dict[str, Any]] = []

    setup_errors = setup_package_errors(setup) if setup else []
    for message in setup_errors:
        issues.append(
            validation_issue(
                "v3_setup_package_invalid",
                "error",
                "",
                message,
                "blocked",
            )
        )

    if manifest_error:
        issues.append(
            validation_issue(
                "root_manifest_invalid",
                "error",
                "_memova/manifest.json",
                f"V3 root manifest is missing or invalid: {manifest_error}",
                "blocked",
            )
        )
    elif (manifest or {}).get("vault_template_version") != template_version:
        issues.append(
            validation_issue(
                "root_manifest_template_mismatch",
                "error",
                "_memova/manifest.json",
                f"Root manifest does not declare {template_version}.",
                "blocked",
            )
        )

    expected_dirs, expected_files, expected_specs = v3_validation_expectations(
        setup=setup,
        tree_manifest=tree_manifest,
    )
    if tree_manifest_error and not setup:
        issues.append(
            validation_issue(
                "tree_manifest_invalid",
                "error",
                "_memova/tree_manifest.json",
                f"V3 tree manifest is missing or invalid: {tree_manifest_error}",
                "blocked",
            )
        )

    for relative_path in expected_dirs:
        target = safe_join(root, relative_path)
        if target.exists() and not target.is_dir():
            blocked_directories.append(relative_path)
            issues.append(
                validation_issue(
                    "required_directory_blocked_by_file",
                    "error",
                    relative_path,
                    "Required Memova V3 directory path is occupied by a non-directory item.",
                    "blocked",
                )
            )
        elif not target.is_dir():
            missing_directories.append(relative_path)
            issues.append(
                validation_issue(
                    "required_directory_missing",
                    "error",
                    relative_path,
                    "Required Memova V3 directory is missing.",
                    "auto" if setup else "blocked",
                    repair_action="create_directory" if setup else None,
                )
            )

    for relative_path in expected_files:
        target = safe_join(root, relative_path)
        if target.exists() and not target.is_file():
            blocked_files.append(relative_path)
            issues.append(
                validation_issue(
                    "required_file_blocked_by_non_file",
                    "error",
                    relative_path,
                    "Required Memova V3 file path is occupied by a non-file item.",
                    "blocked",
                )
            )
            continue
        if not target.is_file():
            missing_files.append(relative_path)
            issues.append(
                validation_issue(
                    "required_file_missing",
                    "error",
                    relative_path,
                    "Required Memova V3 file is missing.",
                    "auto" if setup else "blocked",
                    repair_action="create_file" if setup else None,
                )
            )
            continue
    machine_schemas = (
        V3_MACHINE_JSON_SCHEMA_VERSIONS if template_version == V3_TEMPLATE_VERSION else {}
    )
    for relative_path, expected_schema_version in machine_schemas.items():
        target = safe_join(root, relative_path)
        if not target.is_file():
            continue
        data, error = read_json_file(target)
        if error or (data or {}).get("schema_version") != expected_schema_version:
            issue = {
                "relative_path": relative_path,
                "code": "machine_json_invalid" if error else "machine_json_schema_mismatch",
                "expected": expected_schema_version,
                "actual": (data or {}).get("schema_version") if not error else None,
                "error": error,
            }
            if not any(
                existing.get("relative_path") == relative_path
                and existing.get("code") == issue["code"]
                for existing in machine_json_issues
            ):
                machine_json_issues.append(issue)
                issues.append(
                    validation_issue(
                        str(issue["code"]),
                        "error",
                        relative_path,
                        "Required machine JSON does not match the Memova V3 contract.",
                        "auto" if setup and relative_path in expected_specs else "blocked",
                        repair_action=(
                            "replace_machine_file"
                            if setup and relative_path in expected_specs
                            else None
                        ),
                        details={key: value for key, value in issue.items() if key != "relative_path"},
                    )
                )

    blocked_reasons = [
        issue["message"]
        for issue in issues
        if issue.get("severity") == "error" and issue.get("repairability") == "blocked"
    ]
    error_count = len([issue for issue in issues if issue.get("severity") == "error"])
    status = "blocked" if blocked_reasons else "repair_required" if error_count else "ok"
    health = "blocked" if blocked_reasons else "repairable" if error_count else "healthy"
    repair_package = v3_validation_repair_package(
        template_version=template_version,
        setup=setup,
        expected_specs=expected_specs,
        missing_directories=missing_directories,
        missing_files=missing_files,
        machine_json_issues=machine_json_issues,
        blocked_reasons=blocked_reasons,
    )
    return {
        "schema_version": (
            V4_VALIDATION_RESULT_SCHEMA_VERSION
            if template_version == V4_TEMPLATE_VERSION
            else V3_VALIDATION_RESULT_SCHEMA_VERSION
        ),
        "status": status,
        "health": health,
        "path": str(resolved(root)),
        "target_kind": (
            "memova_managed_root"
            if (manifest or {}).get("setup_mode") == "connect_existing_vault"
            else "memova_vault"
        ),
        "vault_template_version": template_version,
        "memova_input_root_path": str(resolved(root)),
        "memova_input_root_relative_path": (manifest or {}).get(
            "memova_input_root_relative_path",
            ".",
        ),
        "missing_directories": missing_directories,
        "missing_files": missing_files,
        "blocked_directories": blocked_directories,
        "blocked_files": blocked_files,
        "machine_json_issues": machine_json_issues,
        "issues": issues,
        "repair_package": repair_package,
        "vault_manifest_id": (manifest or {}).get("manifest_id"),
        "input_root_manifest_id": (manifest or {}).get("input_root_manifest_id"),
        "manifest_id": (manifest or {}).get("manifest_id"),
        "manifest_error": manifest_error,
        "tree_manifest_error": tree_manifest_error,
        "summary": {
            "issue_count": len(issues),
            "error_count": error_count,
            "blocked_issue_count": len(blocked_reasons),
            "validation_source": "backend_setup_operations" if setup else "local_v3_manifests",
            "blob_mirror_validation": "not_in_scope",
        },
    }


def v3_validation_expectations(
    *,
    setup: dict[str, Any] | None,
    tree_manifest: dict[str, Any] | None,
) -> tuple[list[str], list[str], dict[str, FileSpec]]:
    if setup:
        specs = build_file_specs(setup, target_root=Path("."))
        return build_dirs(setup), [spec.path for spec in specs], {spec.path: spec for spec in specs}
    tree_manifest = tree_manifest or {}
    directories = []
    files = []
    for item in tree_manifest.get("required_directories") or []:
        relative_path = strict_relative_path(item.get("relative_path")) if isinstance(item, dict) else None
        if relative_path:
            directories.append(relative_path)
    for item in tree_manifest.get("required_files") or []:
        relative_path = strict_relative_path(item.get("relative_path")) if isinstance(item, dict) else None
        if relative_path:
            files.append(relative_path)
    return directories, files, {}


def v3_validation_repair_package(
    *,
    template_version: str,
    setup: dict[str, Any] | None,
    expected_specs: dict[str, FileSpec],
    missing_directories: list[str],
    missing_files: list[str],
    machine_json_issues: list[dict[str, Any]],
    blocked_reasons: list[str],
) -> dict[str, Any] | None:
    repair_paths = set(missing_files)
    repair_paths.update(
        str(item.get("relative_path"))
        for item in machine_json_issues
        if item.get("relative_path") in expected_specs
    )
    if not missing_directories and not repair_paths and not blocked_reasons:
        return None
    if setup is None:
        status = "not_available"
        package_blocked_reasons = [
            *blocked_reasons,
            "Current backend setup or repair operations are required; the plugin will not reconstruct V3/V4 files locally.",
        ]
    else:
        status = "not_available" if blocked_reasons else "available"
        package_blocked_reasons = blocked_reasons
    files = [
        validation_file_operation(
            expected_specs[relative_path],
            replace=relative_path not in missing_files,
        )
        for relative_path in sorted(repair_paths)
        if relative_path in expected_specs
    ]
    return {
        "schema_version": (
            V4_REPAIR_PACKAGE_SCHEMA_VERSION
            if template_version == V4_TEMPLATE_VERSION
            else V3_REPAIR_PACKAGE_SCHEMA_VERSION
        ),
        "status": status,
        "generated_at": utc_now_iso(),
        "target_kind": "memova_managed_root",
        "memova_root_relative_path": ".",
        "directories": [
            {
                "relative_path": relative_path,
                "role": f"memova_root_structure_{template_version.rsplit('_', 1)[-1]}",
                "write_mode": "create",
            }
            for relative_path in missing_directories
        ] if setup else [],
        "files": files if setup else [],
        "blocked_reasons": package_blocked_reasons,
        "safety_policy": {
            "scope": "backend_supplied_memova_managed_root_operations_only",
            "never_repairs": [
                "user_modified_non_machine_files",
                "files_not_present_in_backend_setup_operations",
                "cloud_or_blob_mirror_state",
            ],
        },
    }


def validate_v2_vault(path: Path) -> dict[str, Any]:
    root = expand_path(str(path))
    has_v2_root_manifest = safe_join(root, "_memova/manifest.json").is_file()
    is_new_vault = has_v2_root_manifest and root.name != INPUT_ROOT_FOLDER_NAME
    missing_roots: list[str] = []
    missing_machine_files: list[str] = []
    blocked_roots: list[str] = []
    blocked_files: list[str] = []
    invalid_required_files: list[dict[str, Any]] = []
    machine_json_issues: list[dict[str, Any]] = []
    input_root = root

    if has_v2_root_manifest:
        for root_path in NEW_VAULT_REQUIRED_ROOTS:
            target = safe_join(root, root_path.rstrip("/"))
            if root_path.endswith("/") and target.exists() and not target.is_dir():
                blocked_roots.append(root_path)
            elif not target.exists():
                missing_roots.append(root_path)
        invalid_required_files.extend(validate_doc_content(root, NEW_VAULT_DOC_CHECKS, min_chars=120))

    for relative_path in INPUT_ROOT_REQUIRED_FILES:
        target = safe_join(input_root, relative_path)
        if target.exists() and not target.is_file():
            blocked_files.append(relative_path)
        elif not target.is_file():
            missing_machine_files.append(relative_path)
    input_doc_issues = validate_doc_content(input_root, INPUT_ROOT_DOC_CHECKS, min_chars=240)
    invalid_required_files.extend(input_doc_issues)

    manifest_path = safe_join(input_root, "_memova/manifest.json")
    manifest: dict[str, Any] | None = None
    manifest_error: str | None = None
    if manifest_path.exists():
        manifest, manifest_error = read_json_file(manifest_path)

    for relative_path, expected_schema_version in MACHINE_JSON_SCHEMA_VERSIONS.items():
        target = safe_join(input_root, relative_path)
        if not target.is_file():
            continue
        data, error = read_json_file(target)
        if error:
            machine_json_issues.append(
                {
                    "relative_path": relative_path,
                    "code": "machine_json_invalid",
                    "error": error,
                }
            )
            continue
        actual_schema_version = (data or {}).get("schema_version")
        if actual_schema_version != expected_schema_version:
            machine_json_issues.append(
                {
                    "relative_path": relative_path,
                    "code": "machine_json_schema_mismatch",
                    "expected": expected_schema_version,
                    "actual": actual_schema_version,
                }
            )

    issues = validation_issues(
        missing_roots=missing_roots,
        missing_machine_files=missing_machine_files,
        invalid_required_files=invalid_required_files,
        machine_json_issues=machine_json_issues,
        blocked_roots=blocked_roots,
        blocked_files=blocked_files,
    )
    blocked_reasons = [
        issue["message"]
        for issue in issues
        if issue.get("severity") == "error" and issue.get("repairability") == "blocked"
    ]
    error_count = len([issue for issue in issues if issue.get("severity") == "error"])
    if blocked_reasons:
        status = "blocked"
        health = "blocked"
    elif error_count:
        status = "repair_required"
        health = "repairable"
    else:
        status = "ok"
        health = "healthy"
    repair_package = validation_repair_package(
        root,
        target_kind="memova_vault" if is_new_vault else "memova_managed_root",
        missing_roots=missing_roots,
        missing_machine_files=missing_machine_files,
        machine_json_issues=machine_json_issues,
        invalid_required_files=invalid_required_files,
        blocked_roots=blocked_roots,
        blocked_files=blocked_files,
        blocked_reasons=blocked_reasons,
    )

    return {
        "schema_version": VALIDATION_RESULT_SCHEMA_VERSION,
        "legacy_schema_version": "memova_vault_validation_v1",
        "status": status,
        "legacy_status": "ok" if status == "ok" else "fail",
        "health": health,
        "path": str(resolved(root)),
        "target_kind": "memova_vault" if is_new_vault else "memova_managed_root",
        "memova_input_root_path": str(resolved(input_root)),
        "memova_input_root_relative_path": manifest.get("memova_input_root_relative_path", ".")
        if manifest
        else ".",
        "missing_roots": missing_roots,
        "missing_machine_files": missing_machine_files,
        "blocked_roots": blocked_roots,
        "blocked_files": blocked_files,
        "invalid_required_files": invalid_required_files,
        "machine_json_issues": machine_json_issues,
        "issues": issues,
        "repair_package": repair_package,
        "vault_manifest_id": manifest.get("manifest_id") if manifest else None,
        "input_root_manifest_id": manifest.get("input_root_manifest_id") if manifest else None,
        "manifest_id": manifest.get("manifest_id") if manifest else None,
        "manifest_error": manifest_error,
        "summary": {
            "issue_count": len(issues),
            "error_count": error_count,
            "blocked_issue_count": len(blocked_reasons),
            "blob_mirror_validation": "not_in_scope",
            "observation_root": "memova_managed_root_relative_paths",
        },
    }


def validation_issues(
    *,
    missing_roots: list[str],
    missing_machine_files: list[str],
    invalid_required_files: list[dict[str, Any]],
    machine_json_issues: list[dict[str, Any]],
    blocked_roots: list[str],
    blocked_files: list[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for relative_path in missing_roots:
        if relative_path.endswith("/"):
            issues.append(
                validation_issue(
                    "required_directory_missing",
                    "error",
                    relative_path.rstrip("/"),
                    "Required Memova V2 directory is missing.",
                    "auto",
                    repair_action="create_directory",
                )
            )
    for relative_path in missing_machine_files:
        issues.append(
            validation_issue(
                "required_file_missing",
                "error",
                relative_path,
                "Required Memova V2 file is missing.",
                "auto",
                repair_action="create_file",
            )
        )
    for relative_path in blocked_roots:
        issues.append(
            validation_issue(
                "required_directory_blocked_by_file",
                "error",
                relative_path.rstrip("/"),
                "Required Memova V2 directory path is occupied by a non-directory item.",
                "blocked",
            )
        )
    for relative_path in blocked_files:
        issues.append(
            validation_issue(
                "required_file_blocked_by_non_file",
                "error",
                relative_path,
                "Required Memova V2 file path is occupied by a non-file item.",
                "blocked",
            )
        )
    for item in machine_json_issues:
        issues.append(
            validation_issue(
                str(item.get("code") or "machine_json_invalid"),
                "error",
                str(item.get("relative_path") or ""),
                "Required machine JSON does not match the Memova V2 contract.",
                "auto",
                repair_action="replace_machine_file",
                details={key: value for key, value in item.items() if key != "relative_path"},
            )
        )
    for item in invalid_required_files:
        issues.append(
            validation_issue(
                "setup_doc_invalid",
                "error",
                str(item.get("relative_path") or ""),
                "Memova-managed setup document is missing required contract text.",
                "needs_overwrite_approval",
                details=item,
            )
        )
    return issues


def validation_issue(
    code: str,
    severity: str,
    relative_path: str,
    message: str,
    repairability: str,
    *,
    repair_action: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "relative_path": relative_path,
        "message": message,
        "repairability": repairability,
        "repair_action": repair_action,
        "details": details or {},
    }


def validation_repair_package(
    root: Path,
    *,
    target_kind: str,
    missing_roots: list[str],
    missing_machine_files: list[str],
    machine_json_issues: list[dict[str, Any]],
    invalid_required_files: list[dict[str, Any]],
    blocked_roots: list[str],
    blocked_files: list[str],
    blocked_reasons: list[str],
) -> dict[str, Any] | None:
    if not (
        missing_roots
        or missing_machine_files
        or machine_json_issues
        or invalid_required_files
        or blocked_roots
        or blocked_files
    ):
        return None
    blocked_file_set = set(blocked_files)
    directories = [
        {
            "relative_path": relative_path.rstrip("/"),
            "role": "memova_root_structure",
            "write_mode": "create",
        }
        for relative_path in missing_roots
        if relative_path.endswith("/") and relative_path not in blocked_roots
    ]
    repair_setup = {
        "schema_version": SETUP_SCHEMA_VERSION,
        "setup_session_id": "local-validation",
        "workspace_id": None,
        "setup_mode": "create_new_vault" if target_kind == "memova_vault" else "connect_existing_vault",
        "storage_target": "icloud_drive",
        "vault_template_version": TEMPLATE_VERSION,
    }
    specs_by_path = {
        spec.path: spec for spec in build_file_specs(repair_setup, target_root=root)
    }
    repair_file_paths = set(missing_machine_files)
    repair_file_paths.update(
        str(item.get("relative_path"))
        for item in machine_json_issues
        if item.get("relative_path")
    )
    files = [
        validation_file_operation(specs_by_path[relative_path], replace=relative_path not in missing_machine_files)
        for relative_path in sorted(repair_file_paths)
        if relative_path in specs_by_path and relative_path not in blocked_file_set
    ]
    if blocked_reasons:
        status = "not_available"
    elif directories or files:
        status = "available"
    else:
        status = "not_available"
    return {
        "schema_version": REPAIR_PACKAGE_SCHEMA_VERSION,
        "status": status,
        "generated_at": utc_now_iso(),
        "target_kind": target_kind,
        "memova_root_relative_path": ".",
        "directories": directories,
        "files": files,
        "blocked_reasons": blocked_reasons,
        "warnings": [
            "Some setup documents require explicit overwrite approval."
            for _item in invalid_required_files
        ],
        "safety_policy": {
            "scope": "memova_managed_root_v2_structure_only",
            "safe_repairs": [
                "create_missing_required_directories",
                "create_missing_required_files_from_setup_contract",
                "replace_invalid_machine_json_from_setup_contract",
            ],
            "never_repairs": [
                "inbox_packet_source_files",
                "user_created_wiki_or_project_content",
                "cloud_or_blob_mirror_state",
                "manifest_identity_mismatches",
            ],
        },
    }


def validation_file_operation(spec: FileSpec, *, replace: bool) -> dict[str, Any]:
    content_bytes = spec.content.encode("utf-8")
    return {
        "relative_path": spec.path,
        "role": spec.role or validation_file_role(spec.path),
        "content_type": spec.content_type or (
            "application/json" if spec.path.endswith(".json") else "text/markdown"
        ),
        "encoding": "utf-8",
        "write_mode": "replace_machine_file" if replace or spec.path.startswith("_memova/") else "skip_if_exists",
        "sha256": hashlib.sha256(content_bytes).hexdigest(),
        "byte_size": len(content_bytes),
        "content": spec.content,
        "machine_managed": spec.machine,
        "memova_uri": spec.memova_uri,
        "expected_existing_sha256": spec.expected_existing_sha256,
        "preserve_if_modified": spec.preserve_if_modified,
    }


def validation_file_role(relative_path: str) -> str:
    if relative_path == "index.md":
        return "root_index"
    if relative_path == "README.md":
        return "root_readme"
    if relative_path == "AGENTS.md":
        return "root_agents"
    if relative_path == "log.md":
        return "root_log"
    if relative_path.startswith("schemas/"):
        return "schema"
    if relative_path.startswith("_memova/"):
        return Path(relative_path).stem
    if relative_path.endswith("index.md"):
        return "area_index"
    return "setup_doc"


def setup_identity_validation(path: Path, setup: dict[str, Any]) -> dict[str, Any]:
    root = expand_path(str(path))
    validation = validate_vault(root, setup=setup)
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
        actual_input_manifest_id = input_manifest.get("input_root_manifest_id") or input_manifest.get("manifest_id")
        expect("input_root_manifest_id", expected_input_root_manifest_id, actual_input_manifest_id, path_label=str(input_manifest_path))
        expect(
            "setup_session_id",
            setup_session_id,
            input_manifest.get("setup_session_id"),
            path_label=str(input_manifest_path),
        )
        expect("manifest_id", expected_vault_manifest_id, input_manifest.get("manifest_id"), path_label=str(input_manifest_path))

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
            input_manifest.get("input_root_manifest_id") or input_manifest.get("manifest_id")
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
