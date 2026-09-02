#!/usr/bin/env python3
"""Local, consent-aware manifest for Memova Agent output archiving.

The helper never enumerates a repository or Codex history. Scheduled runs may only inspect exact
source paths previously added to this Plugin-owned manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "memova_agent_archive_local_v1"
MCP_SCHEMA_VERSION = "memova_agent_archive_v1"
MAX_BYTES = 500_000
ALLOWED_SUFFIXES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
}
BLOCKED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "logs",
    "tmp",
    "temp",
    "__pycache__",
}
BLOCKED_NAMES = {
    ".env",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "secrets.json",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.I),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(
        r"(?i)\b(?:password|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"client[_-]?secret|secret)\b\s*[:=]\s*['\"]?[^\s,'\";]{4,}"
    ),
)


class ArchiveError(RuntimeError):
    pass


def _state_path() -> Path:
    override = os.environ.get("MEMOVA_AGENT_ARCHIVE_STATE")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".memova" / "codex-agent-archive.json"


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "explicit_only",
        "vault_root": None,
        "authorized_outputs": {},
        "asked_task_ids": [],
        "updated_at": None,
    }


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return _empty_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ArchiveError("Unsupported Agent archive local-state schema.")
    return data


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(UTC).isoformat()
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_source(path: Path) -> tuple[bytes, str]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ArchiveError("Authorized output path is not a regular file.")
    if path.name.casefold() in BLOCKED_NAMES:
        raise ArchiveError("Credential and environment files cannot be archived.")
    if any(part.startswith(".") or part.casefold() in BLOCKED_DIRS for part in path.parts):
        raise ArchiveError("Hidden, dependency, build, cache, temporary, and log paths are excluded.")
    content_type = ALLOWED_SUFFIXES.get(path.suffix.casefold())
    if content_type is None:
        raise ArchiveError("Only Markdown, HTML, and plain-text final outputs are supported.")
    data = path.read_bytes()
    if not data or len(data) > MAX_BYTES or b"\x00" in data:
        raise ArchiveError("Output must be non-empty UTF-8 text no larger than 500000 bytes.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArchiveError("Output must be UTF-8 text.") from exc
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise ArchiveError("Output appears to contain Restricted Data; filter it before archiving.")
    lowered = text.casefold()
    if "<!-- memova-" in lowered or "<!--memova-" in lowered or "memova-link:v1" in lowered:
        raise ArchiveError("Output contains a reserved Memova control marker.")
    return data, content_type


def _configured_root(state: dict[str, Any]) -> Path:
    raw = state.get("vault_root")
    if not isinstance(raw, str) or not raw:
        raise ArchiveError("Configure the bound Memova Knowledge Base path first.")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ArchiveError("Configured Memova Knowledge Base path is unavailable.")
    destination = root / "projects" / "Uncategorized"
    destination.mkdir(parents=True, exist_ok=True)
    return root


def _manifest_key(path: Path) -> str:
    return hashlib.sha256(str(path.expanduser().resolve()).encode("utf-8")).hexdigest()


def _copy_authorized(
    *,
    state: dict[str, Any],
    source: Path,
    data: bytes,
    entry: dict[str, Any],
) -> Path:
    root = _configured_root(state)
    destination = root / str(entry["relative_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    current_hash = _sha(destination.read_bytes()) if destination.exists() else None
    expected_hash = entry.get("local_sha256")
    if current_hash is not None and expected_hash is None:
        if current_hash != _sha(data):
            raise ArchiveError("Uncategorized destination already exists with different content.")
    elif current_hash is not None and current_hash not in {expected_hash, _sha(data)}:
        raise ArchiveError("Uncategorized destination changed outside the authorized workflow.")
    handle, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(handle)
    try:
        shutil.copyfile(source, temp_name)
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    entry["local_sha256"] = _sha(data)
    return destination


def _request(
    *,
    state: dict[str, Any],
    source: Path,
    task_id: str,
    source_reference: str,
    title: str | None,
    source_kind: str,
    archive_mode: str,
    authorize: bool,
) -> dict[str, Any]:
    data, content_type = _validate_source(source)
    key = _manifest_key(source)
    entries = state["authorized_outputs"]
    entry = entries.get(key)
    persistent_authorization = archive_mode in {"always_auto_save", "scheduled"}
    if entry is None:
        if not authorize:
            raise ArchiveError("This exact output has not been authorized for Memova archiving.")
        entry = {
            "source_path": str(source.expanduser().resolve()),
            "stable_node_id": str(uuid.uuid4()),
            "relative_path": f"projects/Uncategorized/{source.name}",
            "persistent_authorization": persistent_authorization,
            "last_synced_sha256": None,
            "local_sha256": None,
        }
        entries[key] = entry
    elif archive_mode == "scheduled" and not entry.get("persistent_authorization"):
        raise ArchiveError("Scheduled runs require a previously authorized manifest entry.")
    elif authorize and persistent_authorization:
        entry["persistent_authorization"] = True
    destination = _copy_authorized(state=state, source=source, data=data, entry=entry)
    entry.update(
        {
            "source_task_id": task_id,
            "source_reference": source_reference,
            "source_kind": source_kind,
            "content_type": content_type,
            "current_sha256": _sha(data),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    _save_state(state)
    idempotency = hashlib.sha256(
        f"{entry['stable_node_id']}:{_sha(data)}:{source_reference}".encode("utf-8")
    ).hexdigest()
    return {
        "tool": (
            "import_codex_task_markdown"
            if source_kind == "codex_task_markdown"
            else "import_agent_file"
        ),
        "arguments": {
            "schema_version": MCP_SCHEMA_VERSION,
            "stable_node_id": entry["stable_node_id"],
            "idempotency_key": idempotency,
            "source_kind": source_kind,
            "source_task_id": task_id,
            "source_reference": source_reference,
            "title": (title or source.stem)[:255],
            "relative_path": entry["relative_path"],
            "content_type": content_type,
            "content": data.decode("utf-8"),
            "content_sha256": _sha(data),
            "archive_mode": archive_mode,
            "user_authorized": True,
            "authorized_manifest_entry": bool(entry.get("persistent_authorization")),
            "current_task_selected": source_kind == "codex_task_markdown",
        },
        "local_destination": str(destination),
    }


def command_configure(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state()
    root = Path(args.vault_root).expanduser().resolve()
    if not root.is_dir():
        raise ArchiveError("Knowledge Base root must already exist and be a directory.")
    (root / "projects" / "Uncategorized").mkdir(parents=True, exist_ok=True)
    state["vault_root"] = str(root)
    state["mode"] = args.mode
    _save_state(state)
    return {"status": "configured", "vault_root": str(root), "mode": args.mode}


def command_prepare(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state()
    mode = args.mode or state.get("mode") or "explicit_only"
    if args.scheduled:
        mode = "scheduled"
    if mode in {"explicit_only", "ask_each_time"} and not args.authorize:
        raise ArchiveError("This archive mode requires adjacent user authorization.")
    return _request(
        state=state,
        source=Path(args.source),
        task_id=args.task_id,
        source_reference=args.source_reference,
        title=args.title,
        source_kind=args.source_kind,
        archive_mode=mode,
        authorize=args.authorize or mode == "always_auto_save",
    )


def command_scan(_: argparse.Namespace) -> dict[str, Any]:
    state = _load_state()
    requests = []
    for entry in list(state["authorized_outputs"].values()):
        if not entry.get("persistent_authorization"):
            continue
        source = Path(str(entry["source_path"]))
        try:
            data, _content_type = _validate_source(source)
        except ArchiveError as exc:
            requests.append({"source_path": str(source), "status": "blocked", "reason": str(exc)})
            continue
        if _sha(data) == entry.get("last_synced_sha256"):
            continue
        try:
            requests.append(
                _request(
                    state=state,
                    source=source,
                    task_id=str(entry.get("source_task_id") or "scheduled-authorized-output"),
                    source_reference=str(entry.get("source_reference") or f"file://{source}"),
                    title=None,
                    source_kind=str(entry.get("source_kind") or "agent_file"),
                    archive_mode="scheduled",
                    authorize=False,
                )
            )
        except ArchiveError as exc:
            requests.append({"source_path": str(source), "status": "blocked", "reason": str(exc)})
    return {"schema_version": SCHEMA_VERSION, "requests": requests}


def command_mark_synced(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state()
    key = _manifest_key(Path(args.source))
    entry = state["authorized_outputs"].get(key)
    if entry is None or entry.get("current_sha256") != args.sha256:
        raise ArchiveError("Sync ACK does not match the current authorized output hash.")
    entry["last_synced_sha256"] = args.sha256
    entry["last_synced_at"] = datetime.now(UTC).isoformat()
    _save_state(state)
    return {"status": "synced", "stable_node_id": entry["stable_node_id"]}


def command_ask_status(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state()
    asked = args.task_id in set(state.get("asked_task_ids") or [])
    return {"task_id": args.task_id, "should_ask": not asked, "already_asked": asked}


def command_mark_asked(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state()
    asked = set(state.get("asked_task_ids") or [])
    asked.add(args.task_id)
    state["asked_task_ids"] = sorted(asked)[-500:]
    _save_state(state)
    return {"task_id": args.task_id, "already_asked": True}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Prepare authorized Memova Agent archives.")
    sub = root.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure")
    configure.add_argument("--vault-root", required=True)
    configure.add_argument(
        "--mode",
        choices=("explicit_only", "ask_each_time", "always_auto_save"),
        default="explicit_only",
    )
    configure.set_defaults(handler=command_configure)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--task-id", required=True)
    prepare.add_argument("--source-reference", required=True)
    prepare.add_argument("--title")
    prepare.add_argument(
        "--source-kind", choices=("agent_file", "codex_task_markdown"), default="agent_file"
    )
    prepare.add_argument(
        "--mode", choices=("explicit_only", "ask_each_time", "always_auto_save")
    )
    prepare.add_argument("--authorize", action="store_true")
    prepare.add_argument("--scheduled", action="store_true")
    prepare.set_defaults(handler=command_prepare)
    scan = sub.add_parser("scan-authorized")
    scan.set_defaults(handler=command_scan)
    synced = sub.add_parser("mark-synced")
    synced.add_argument("--source", required=True)
    synced.add_argument("--sha256", required=True)
    synced.set_defaults(handler=command_mark_synced)
    ask = sub.add_parser("ask-status")
    ask.add_argument("--task-id", required=True)
    ask.set_defaults(handler=command_ask_status)
    mark = sub.add_parser("mark-asked")
    mark.add_argument("--task-id", required=True)
    mark.set_defaults(handler=command_mark_asked)
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        result = args.handler(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ArchiveError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
