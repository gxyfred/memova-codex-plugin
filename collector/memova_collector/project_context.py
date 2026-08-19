from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

PROJECT_CONTEXT_SCHEMA_VERSION = "memova_codex_project_context_v1"


def build_project_context(
    thread: dict[str, Any],
    *,
    fingerprint_secret: str | None,
    workspace_fingerprint_key: str | None = None,
    include_observations: bool = False,
) -> dict[str, Any] | None:
    """Build a useful context envelope without exporting paths or repository URLs."""

    if not fingerprint_secret:
        return None
    git_info = thread.get("gitInfo") or thread.get("git_info")
    if not isinstance(git_info, dict):
        git_info = {}
    cwd = _clean_text(thread.get("cwd"))
    origin = _clean_text(git_info.get("originUrl") or git_info.get("origin_url"))
    remote_identity, remote_display_name = _normalized_remote_identity(origin)
    repository_root = _find_repository_root(cwd)
    local_identity = str(repository_root or Path(cwd).expanduser()) if cwd else None
    use_workspace_identity = bool(remote_identity and workspace_fingerprint_key)
    identity = remote_identity if use_workspace_identity else local_identity
    if not identity:
        return None

    if use_workspace_identity:
        repository_fingerprint = "hmac-sha256-v1:" + hmac.new(
            str(workspace_fingerprint_key).encode("utf-8"),
            identity.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        repository_identity_kind = "workspace_hmac_remote"
    else:
        repository_fingerprint = (
            f"opaque-v1:{_opaque_repository_id(fingerprint_secret, identity)}"
        )
        repository_identity_kind = "device_local_opaque"
    context: dict[str, Any] = {
        "schema_version": PROJECT_CONTEXT_SCHEMA_VERSION,
        "repository_fingerprint": repository_fingerprint,
        "repository_identity_kind": repository_identity_kind,
        "memova_context_uris": [],
    }
    if include_observations:
        display_name = remote_display_name or (
            repository_root.name if repository_root is not None else None
        )
        if display_name:
            context["repository_display_name"] = display_name[:200]
        branch = _clean_text(git_info.get("branch"))
        if branch:
            context["branch"] = branch[:255]
        working_path = _repository_relative_working_path(cwd, repository_root)
        if working_path is not None:
            context["working_path"] = working_path
    return context


def _opaque_repository_id(secret: str, identity: str) -> uuid.UUID:
    digest = bytearray(
        hmac.new(
            secret.encode("utf-8"),
            identity.encode("utf-8"),
            hashlib.sha256,
        ).digest()[:16]
    )
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(digest))


def _normalized_remote_identity(origin: str | None) -> tuple[str | None, str | None]:
    if not origin:
        return None, None
    value = origin.strip()
    host: str | None = None
    path: str | None = None
    if "://" in value:
        parsed = urlsplit(value)
        host = parsed.hostname.lower() if parsed.hostname else None
        try:
            port = parsed.port
        except ValueError:
            return None, None
        if host and port:
            host = f"{host}:{port}"
        path = unquote(parsed.path or "")
    elif ":" in value:
        scp_host, scp_path = value.split(":", 1)
        host = scp_host.rsplit("@", 1)[-1].strip().lower() or None
        path = scp_path
    if not host or not path:
        return None, None
    normalized_path = "/".join(
        part for part in PurePosixPath(path.replace("\\", "/")).parts if part not in {"/", ""}
    ).strip("/")
    if normalized_path.endswith(".git"):
        normalized_path = normalized_path[:-4]
    if not normalized_path:
        return None, None
    display_name = normalized_path.rsplit("/", 1)[-1]
    return f"remote:{host}/{normalized_path}", display_name


def _find_repository_root(cwd: str | None) -> Path | None:
    if not cwd:
        return None
    try:
        current = Path(cwd).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    if not current.is_dir():
        return None
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _repository_relative_working_path(
    cwd: str | None,
    repository_root: Path | None,
) -> str | None:
    if not cwd or repository_root is None:
        return None
    try:
        relative = Path(cwd).expanduser().resolve(strict=False).relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return None
    value = relative.as_posix() or "."
    if value.startswith(("/", "~", "\\")) or "\\" in value:
        return None
    if any(part in {"", ".."} for part in value.split("/")):
        return None
    return value[:2048]


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, (str, os.PathLike)):
        return None
    cleaned = str(value).strip()
    return cleaned or None
