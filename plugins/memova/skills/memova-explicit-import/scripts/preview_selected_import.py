#!/usr/bin/env python3
"""Create a content-safe preview for one explicitly selected UTF-8 input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = "memova_selected_import_preview_v1"
SCAN_VERSION = "memova_restricted_data_scan_v1"
MAX_INPUT_BYTES = 100_000
SELECTION_KINDS = ("excerpt", "task", "date_range", "uploaded_resource")

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?"
            r"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("authorization_bearer", re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._~+/=-]{12,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b")),
    ("github_token", re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)(?P<prefix>\b(?:password|passwd|pwd|api[_-]?key|access[_-]?token|"
            r"refresh[_-]?token|client[_-]?secret|secret)\b\s*[:=]\s*)"
            r"(?!\[REDACTED:)(?P<quote>['\"]?)(?P<value>[^\s,'\";]{4,})(?P=quote)"
        ),
    ),
    (
        "credential_url",
        re.compile(r"(?i)(?P<prefix>\b[a-z][a-z0-9+.-]*://[^\s/:@]+:)(?P<value>[^\s/@]+)(?=@)"),
    ),
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sanitize_text(value: str) -> tuple[str, Counter[str]]:
    sanitized = value
    findings: Counter[str] = Counter()
    for kind, pattern in PATTERNS:
        def replace(match: re.Match[str]) -> str:
            findings[kind] += 1
            groups = match.groupdict()
            prefix = groups.get("prefix") or ""
            return f"{prefix}[REDACTED:{kind.upper()}]"

        sanitized = pattern.sub(replace, sanitized)
    return sanitized, findings


def _read_input(args: argparse.Namespace) -> str:
    if args.stdin:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        path = Path(args.input_file).expanduser()
        if not path.is_file():
            raise RuntimeError("The explicitly selected input is not a regular file.")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise RuntimeError(f"Selected input exceeds {MAX_INPUT_BYTES} UTF-8 bytes.")
        raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise RuntimeError(f"Selected input exceeds {MAX_INPUT_BYTES} UTF-8 bytes.")
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Selected input must be valid UTF-8 text.") from exc
    if "\x00" in value:
        raise RuntimeError("Selected input contains NUL bytes and is not treated as text.")
    return value


def _atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(value, encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="preview_selected_import.py")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-file")
    source.add_argument("--stdin", action="store_true")
    parser.add_argument("--selection-kind", required=True, choices=SELECTION_KINDS)
    parser.add_argument("--source-label", required=True)
    parser.add_argument(
        "--source-reference",
        help="Opaque client/user selection id; defaults to the original content hash.",
    )
    parser.add_argument("--output-file")
    parser.add_argument("--include-sanitized", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.source_label.strip() or len(args.source_label) > 200:
            raise RuntimeError("Source label must contain 1-200 characters.")
        original = _read_input(args)
        sanitized, findings = sanitize_text(original)
        original_hash = _sha256(original)
        sanitized_hash = _sha256(sanitized)
        source_reference = (args.source_reference or f"content-sha256:{original_hash}").strip()
        if not source_reference or len(source_reference) > 256:
            raise RuntimeError("Source reference must contain 1-256 characters.")
        preview_created_at = datetime.now(UTC).isoformat()
        preview_id = "preview-" + _sha256(
            "\n".join(
                (
                    args.selection_kind,
                    args.source_label.strip(),
                    source_reference,
                    sanitized_hash,
                    preview_created_at,
                )
            )
        )
        output_path = None
        if args.output_file:
            target = Path(args.output_file).expanduser()
            _atomic_write(target, sanitized)
            output_path = str(target.resolve())
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "scan_version": SCAN_VERSION,
            "preview_id": preview_id,
            "preview_created_at": preview_created_at,
            "selection_kind": args.selection_kind,
            "source_label": args.source_label.strip(),
            "source_reference": source_reference,
            "original": {
                "utf8_bytes": len(original.encode("utf-8")),
                "characters": len(original),
                "sha256": original_hash,
            },
            "sanitized": {
                "utf8_bytes": len(sanitized.encode("utf-8")),
                "characters": len(sanitized),
                "sha256": sanitized_hash,
            },
            "restricted_data": {
                "finding_count": sum(findings.values()),
                "finding_counts_by_type": dict(sorted(findings.items())),
                "values_returned": False,
                "changed": sanitized != original,
            },
            "output_file": output_path,
        }
        if args.include_sanitized:
            payload["sanitized_content"] = sanitized
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
