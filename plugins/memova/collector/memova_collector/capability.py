from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .contracts import ALLOWED_SOURCE_KINDS, COLLECTOR_VERSION, utc_now

DEFAULT_APP_CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
REQUIRED_PROTOCOL_MARKERS = (
    "thread/list",
    "thread/read",
    "includeTurns",
    "userMessage",
    "agentMessage",
    "cwd",
    "gitInfo",
)


def locate_codex(explicit_path: str | None = None) -> Path | None:
    candidates = [
        explicit_path,
        os.environ.get("MEMOVA_CODEX_PATH"),
        shutil.which("codex"),
        str(DEFAULT_APP_CODEX),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path.resolve()
    return None


def _run(args: list[str], *, timeout: float = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def inspect_capabilities(codex_path: str | None = None) -> dict[str, Any]:
    """Inspect generated protocol schemas without reading any conversation data."""

    executable = locate_codex(codex_path)
    report: dict[str, Any] = {
        "schema_version": "memova_codex_app_server_capability_v1",
        "collector_version": COLLECTOR_VERSION,
        "checked_at": utc_now(),
        "supported": False,
        "experimental": True,
        "codex_path": str(executable) if executable else None,
        "codex_version": None,
        "transport": "stdio",
        "required_markers": list(REQUIRED_PROTOCOL_MARKERS),
        "missing_markers": list(REQUIRED_PROTOCOL_MARKERS),
        "source_kinds_supported": [],
        "reasons": [],
    }
    if executable is None:
        report["reasons"].append("codex_executable_not_found")
        return report

    try:
        version_result = _run([str(executable), "--version"])
        report["codex_version"] = version_result.stdout.strip() or version_result.stderr.strip()
        help_result = _run([str(executable), "app-server", "--help"])
    except (OSError, subprocess.SubprocessError) as exc:
        report["reasons"].append(f"codex_probe_failed:{type(exc).__name__}")
        return report

    help_text = f"{help_result.stdout}\n{help_result.stderr}"
    report["experimental"] = "[experimental]" in help_text.lower()
    if help_result.returncode != 0:
        report["reasons"].append("app_server_help_failed")
        return report
    if "stdio://" not in help_text:
        report["reasons"].append("stdio_transport_not_advertised")
        return report

    with tempfile.TemporaryDirectory(prefix="memova-app-server-schema-") as temp_dir:
        output_dir = Path(temp_dir) / "schema"
        try:
            schema_result = _run(
                [
                    str(executable),
                    "app-server",
                    "generate-json-schema",
                    "--out",
                    str(output_dir),
                ],
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            report["reasons"].append(f"schema_generation_failed:{type(exc).__name__}")
            return report
        if schema_result.returncode != 0:
            report["reasons"].append("schema_generation_failed")
            return report
        schema_files = sorted(output_dir.rglob("*.json"))
        schema_text = "\n".join(path.read_text(encoding="utf-8") for path in schema_files)
        missing = [marker for marker in REQUIRED_PROTOCOL_MARKERS if marker not in schema_text]
        report["missing_markers"] = missing
        report["schema_file_count"] = len(schema_files)
        thread_list_schema = next(
            (path for path in schema_files if path.name == "ThreadListParams.json"),
            None,
        )
        if thread_list_schema is not None:
            try:
                payload = json.loads(thread_list_schema.read_text(encoding="utf-8"))
                enum = payload.get("definitions", {}).get("ThreadSourceKind", {}).get("enum", [])
                report["source_kinds_supported"] = [
                    kind for kind in ALLOWED_SOURCE_KINDS if kind in enum
                ]
            except (json.JSONDecodeError, OSError):
                report["reasons"].append("thread_list_schema_unreadable")

    if report["missing_markers"]:
        report["reasons"].append("required_protocol_markers_missing")
    if "appServer" not in report["source_kinds_supported"]:
        report["reasons"].append("desktop_app_source_kind_missing")
    report["supported"] = not report["reasons"]
    return report
