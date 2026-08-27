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

DEFAULT_STATE_PATH = Path.home() / ".cache" / "memova-codex-plugin" / "version-check-v1.json"
DEFAULT_COMPATIBILITY_URL = "https://api.memova.ai/.well-known/memova-plugin-compatibility"
MARKETPLACE_NAME = "memova-codex-plugin"
CHECK_INTERVAL = timedelta(hours=24)
REMINDER_INTERVAL = timedelta(days=1)
NETWORK_TIMEOUT_SECONDS = 4


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the installed Memova Codex plugin is outdated.",
    )
    parser.add_argument("--force", action="store_true", help="Ignore the 24-hour network check cache.")
    parser.add_argument("--current-version", help="Override current version for validation.")
    parser.add_argument("--compatibility-url", help="Override the compatibility endpoint URL.")
    parser.add_argument(
        "--state-path",
        type=Path,
        help="Override the local cache path for validation.",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    state_path = args.state_path or state_path_from_environment()
    state = read_state(state_path)
    state["run_count"] = int(state.get("run_count") or 0) + 1

    current_version = args.current_version or read_current_version()
    compatibility_url = (
        args.compatibility_url
        or os.getenv("MEMOVA_PLUGIN_COMPATIBILITY_URL")
        or DEFAULT_COMPATIBILITY_URL
    )
    compatibility, source, skipped_reason, error = resolve_compatibility(
        state=state,
        compatibility_url=compatibility_url,
        now=now,
        force=args.force,
    )
    latest_version = compatibility.get("latest_version") if compatibility else None
    minimum_supported_version = (
        compatibility.get("minimum_supported_version") if compatibility else None
    )

    update_available = (
        latest_version is not None
        and current_version is not None
        and is_newer_version(latest_version, current_version)
    )
    unsupported_version = (
        minimum_supported_version is not None
        and current_version is not None
        and is_newer_version(minimum_supported_version, current_version)
    )
    should_remind = should_show_update_reminder(
        state=state,
        latest_version=latest_version,
        update_available=update_available,
        now=now,
    )

    state["current_version"] = current_version
    state["compatibility_url"] = compatibility_url
    state["last_update_available"] = update_available
    if should_remind:
        state["last_reminded_at"] = to_iso(now)
        state["last_reminded_version"] = latest_version
    elif not update_available and current_version:
        state["last_reminded_version"] = None
    try:
        write_state(state_path, state)
    except OSError as exc:
        state_error = f"state cache write failed: {exc}"
        error = f"{error}; {state_error}" if error else state_error

    print_json(
        {
            "schema_version": "memova_plugin_version_check_v1",
            "should_remind": should_remind,
            "update_available": update_available,
            "current_version": current_version,
            "latest_version": latest_version,
            "minimum_supported_version": minimum_supported_version,
            "unsupported_version": unsupported_version,
            "latest_source": source,
            "state_path": str(state_path),
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


def resolve_compatibility(
    *,
    state: dict[str, Any],
    compatibility_url: str,
    now: datetime,
    force: bool,
) -> tuple[dict[str, str] | None, str, str | None, str | None]:
    last_checked_at = parse_iso(state.get("last_checked_at"))
    cached_latest = state.get("latest_version")
    cached_minimum = state.get("minimum_supported_version")
    cached_url = state.get("compatibility_url")
    if (
        not force
        and cached_url == compatibility_url
        and last_checked_at is not None
        and now - last_checked_at < CHECK_INTERVAL
    ):
        return (
            compatibility_values(cached_latest, cached_minimum) if cached_latest else None,
            "cache",
            "check_interval_not_elapsed",
            None,
        )

    try:
        compatibility = fetch_compatibility(compatibility_url)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        state["last_checked_at"] = to_iso(now)
        cached_for_url = cached_url == compatibility_url and cached_latest
        cached = compatibility_values(cached_latest, cached_minimum) if cached_for_url else None
        return cached, "cache", "latest_check_failed", str(exc)

    state.update(compatibility)
    state["last_checked_at"] = to_iso(now)
    state["latest_check_error"] = None
    return compatibility, "network", None, None


def fetch_compatibility(compatibility_url: str) -> dict[str, str]:
    request = urllib.request.Request(
        compatibility_url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "memova-codex-plugin-version-check/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("schema_version") != "memova_plugin_compatibility_v1":
        raise ValueError("unsupported compatibility schema")
    if payload.get("plugin_name") != "memova":
        raise ValueError("compatibility response is for a different plugin")
    latest_version = str(payload.get("latest_version") or "").strip()
    minimum_supported_version = str(payload.get("minimum_supported_version") or "").strip()
    if parse_version_parts(latest_version) is None:
        raise ValueError("compatibility response has an invalid latest version")
    if parse_version_parts(minimum_supported_version) is None:
        raise ValueError("compatibility response has an invalid minimum supported version")
    return compatibility_values(latest_version, minimum_supported_version)


def compatibility_values(
    latest_version: Any,
    minimum_supported_version: Any,
) -> dict[str, str]:
    values = {"latest_version": str(latest_version)}
    if minimum_supported_version:
        values["minimum_supported_version"] = str(minimum_supported_version)
    return values


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
    latest = parse_version_parts(latest_version)
    current = parse_version_parts(current_version)
    return latest is not None and current is not None and latest > current


def parse_version_parts(
    version: str,
) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]] | None:
    match = re.fullmatch(
        r"\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?\s*",
        version,
    )
    if not match:
        return None
    major = int(match.group(1) or 0)
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    prerelease = match.group(4)
    if prerelease is None:
        return (major, minor, patch, 1, ())
    prerelease_parts: tuple[tuple[int, int | str], ...] = tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in prerelease.split(".")
    )
    return (major, minor, patch, 0, prerelease_parts)


def update_message(current_version: str | None, latest_version: str | None) -> str:
    current = current_version or "unknown"
    latest = latest_version or "unknown"
    return (
        f"Memova Codex plugin update available: installed {current}, latest {latest}. "
        f"Run `codex plugin marketplace upgrade {MARKETPLACE_NAME}`, then restart Codex or start a new thread."
    )


def state_path_from_environment() -> Path:
    configured = os.getenv("MEMOVA_PLUGIN_VERSION_STATE_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_STATE_PATH


def read_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
