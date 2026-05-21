#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path.home() / ".cache" / "memova-codex-plugin" / "version-check-v1.json"
DEFAULT_LATEST_MANIFEST_URL = (
    "https://raw.githubusercontent.com/gxyfred/memova-codex-plugin/main/"
    "plugins/memova/.codex-plugin/plugin.json"
)
MARKETPLACE_NAME = "memova-codex-plugin"
CHECK_INTERVAL = timedelta(hours=24)
REMINDER_INTERVAL = timedelta(days=7)
NETWORK_TIMEOUT_SECONDS = 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the installed Memova Codex plugin is outdated.")
    parser.add_argument("--force", action="store_true", help="Ignore the 24-hour network check cache.")
    parser.add_argument("--current-version", help="Override current version for validation.")
    parser.add_argument("--latest-manifest-url", help="Override latest manifest URL for validation.")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    state = read_state()
    state["run_count"] = int(state.get("run_count") or 0) + 1

    current_version = args.current_version or read_current_version()
    latest_manifest_url = (
        args.latest_manifest_url
        or os.getenv("MEMOVA_PLUGIN_LATEST_MANIFEST_URL")
        or DEFAULT_LATEST_MANIFEST_URL
    )
    latest_version, source, skipped_reason, error = resolve_latest_version(
        state=state,
        latest_manifest_url=latest_manifest_url,
        now=now,
        force=args.force,
    )

    update_available = (
        latest_version is not None
        and current_version is not None
        and is_newer_version(latest_version, current_version)
    )
    should_remind = should_show_update_reminder(
        state=state,
        latest_version=latest_version,
        update_available=update_available,
        now=now,
    )

    state["current_version"] = current_version
    state["latest_manifest_url"] = latest_manifest_url
    state["last_update_available"] = update_available
    if should_remind:
        state["last_reminded_at"] = to_iso(now)
        state["last_reminded_version"] = latest_version
    elif not update_available and current_version:
        state["last_reminded_version"] = None
    write_state(state)

    print_json(
        {
            "schema_version": "memova_plugin_version_check_v1",
            "should_remind": should_remind,
            "update_available": update_available,
            "current_version": current_version,
            "latest_version": latest_version,
            "latest_source": source,
            "state_path": str(STATE_PATH),
            "skipped_reason": skipped_reason,
            "error": error,
            "message": update_message(current_version, latest_version) if should_remind else None,
        },
    )
    return 0


def read_current_version() -> str | None:
    manifest_path = Path(__file__).resolve().parents[1] / ".codex-plugin" / "plugin.json"
    try:
        return str(json.loads(manifest_path.read_text(encoding="utf-8")).get("version") or "")
    except (OSError, json.JSONDecodeError):
        return None


def resolve_latest_version(
    *,
    state: dict[str, Any],
    latest_manifest_url: str,
    now: datetime,
    force: bool,
) -> tuple[str | None, str, str | None, str | None]:
    last_checked_at = parse_iso(state.get("last_checked_at"))
    cached_latest = state.get("latest_version")
    cached_url = state.get("latest_manifest_url")
    if (
        not force
        and cached_latest
        and cached_url == latest_manifest_url
        and last_checked_at is not None
        and now - last_checked_at < CHECK_INTERVAL
    ):
        return str(cached_latest), "cache", "check_interval_not_elapsed", None

    try:
        latest_version = fetch_latest_version(latest_manifest_url)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        state["last_checked_at"] = to_iso(now)
        cached_for_url = cached_url == latest_manifest_url and cached_latest
        return str(cached_latest) if cached_for_url else None, "cache", "latest_check_failed", str(exc)

    state["latest_version"] = latest_version
    state["last_checked_at"] = to_iso(now)
    state["latest_check_error"] = None
    return latest_version, "network", None, None


def fetch_latest_version(latest_manifest_url: str) -> str:
    request = urllib.request.Request(
        latest_manifest_url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "memova-codex-plugin-version-check/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    version = str(payload.get("version") or "").strip()
    if not version:
        raise ValueError("latest manifest has no version")
    return version


def should_show_update_reminder(
    *,
    state: dict[str, Any],
    latest_version: str | None,
    update_available: bool,
    now: datetime,
) -> bool:
    if not update_available or not latest_version:
        return False
    if state.get("last_reminded_version") != latest_version:
        return True
    last_reminded_at = parse_iso(state.get("last_reminded_at"))
    if last_reminded_at is None:
        return True
    return now - last_reminded_at >= REMINDER_INTERVAL


def is_newer_version(latest_version: str, current_version: str) -> bool:
    return parse_version_parts(latest_version) > parse_version_parts(current_version)


def parse_version_parts(version: str) -> tuple[int, int, int, str]:
    match = re.match(r"^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?([A-Za-z0-9.+_-].*)?\s*$", version)
    if not match:
        return (0, 0, 0, version)
    major = int(match.group(1) or 0)
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    suffix = match.group(4) or ""
    return (major, minor, patch, suffix)


def update_message(current_version: str | None, latest_version: str | None) -> str:
    current = current_version or "unknown"
    latest = latest_version or "unknown"
    return (
        f"Memova Codex plugin update available: installed {current}, latest {latest}. "
        f"Run `codex plugin marketplace upgrade {MARKETPLACE_NAME}`, then restart Codex or start a new thread."
    )


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


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
