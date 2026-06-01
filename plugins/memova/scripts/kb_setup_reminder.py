#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path.home() / ".cache" / "memova-codex-plugin" / "kb-setup-reminder-v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check one-time Memova knowledge-base setup reminder state.")
    parser.add_argument("--mark-complete", action="store_true")
    parser.add_argument("--vault-path")
    parser.add_argument(
        "--backend-completed",
        action="store_true",
        help=(
            "Required with --mark-complete. Set only after complete_knowledge_base_setup "
            "succeeds for the same setup session."
        ),
    )
    parser.add_argument(
        "--setup-session-id",
        help="Backend setup session id that was completed before marking the local reminder complete.",
    )
    args = parser.parse_args()

    state = read_state()
    discovered = discover_vaults(args.vault_path)

    if args.mark_complete:
        if not args.backend_completed or not args.setup_session_id:
            print_json(
                {
                    "schema_version": "memova_kb_setup_reminder_v1",
                    "status": "blocked",
                    "error_code": "backend_setup_completion_required",
                    "error": (
                        "--mark-complete is allowed only after the backend "
                        "complete_knowledge_base_setup call succeeds. Re-run with "
                        "--backend-completed and --setup-session-id after that MCP call."
                    ),
                    "should_remind": True,
                    "state_path": str(STATE_PATH),
                    "discovered_vaults": discovered,
                },
            )
            return 2
        state["completed_at"] = utc_now()
        state["setup_session_id"] = args.setup_session_id
        state["backend_completed"] = True
        if args.vault_path:
            state["vault_path"] = str(Path(args.vault_path).expanduser().resolve(strict=False))
        write_state(state)
        print_json(
            {
                "schema_version": "memova_kb_setup_reminder_v1",
                "status": "complete_marked",
                "should_remind": False,
                "state_path": str(STATE_PATH),
                "discovered_vaults": discovered,
            },
        )
        return 0

    if discovered and not state.get("completed_at"):
        state["completed_at"] = utc_now()
        state["vault_path"] = discovered[0]["vault_path"]
        write_state(state)

    should_remind = not discovered and not state.get("reminded_at") and not state.get("completed_at")
    if should_remind:
        state["reminded_at"] = utc_now()
        write_state(state)

    print_json(
        {
            "schema_version": "memova_kb_setup_reminder_v1",
            "should_remind": should_remind,
            "already_reminded": bool(state.get("reminded_at")) and not should_remind,
            "completed": bool(state.get("completed_at") or discovered),
            "state_path": str(STATE_PATH),
            "discovered_vaults": discovered,
            "message": (
                "Memova knowledge base is not set up on this Mac yet. You can run "
                "'@memova Set up knowledge base.' when you want Codex to create or connect it."
                if should_remind
                else None
            ),
        },
    )
    return 0


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def discover_vaults(extra_path: str | None = None) -> list[dict[str, str]]:
    candidates: list[Path] = []
    home = Path.home()
    if extra_path:
        candidates.append(Path(extra_path).expanduser())
    candidates.extend(
        [
            home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Memova Vault",
            home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Memova",
            home / "Documents" / "Memova Vault",
        ],
    )

    discovered: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        root = candidate.resolve(strict=False)
        manifest = root / "_memova" / "manifest.json"
        key = str(root)
        if key in seen or not manifest.is_file():
            continue
        seen.add(key)
        manifest_id = ""
        try:
            manifest_id = str(json.loads(manifest.read_text(encoding="utf-8")).get("manifest_id") or "")
        except json.JSONDecodeError:
            manifest_id = ""
        discovered.append(
            {
                "vault_path": key,
                "manifest_path": str(manifest),
                "manifest_id": manifest_id,
            },
        )
    return discovered


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
