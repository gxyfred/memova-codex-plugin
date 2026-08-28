#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SERVER_NAME = "memova"
BASE_SCOPES = (
    "notes.read",
    "personal_manual.write",
    "automation.read",
    "automation.write",
    "knowledge.read",
    "knowledge.write",
)
PERSONAL_MANUAL_SCOPES = (
    "notes.read",
    "personal_manual.write",
)
AUTHORIZE_URL_RE = re.compile(r"https://\S+")
SCOPE_RE = re.compile(r"^[a-z][a-z0-9_.:-]*$")
DEFAULT_SCOPE_RECOVERY_STATE_PATH = (
    Path.home() / ".cache" / "memova-codex-plugin" / "oauth-scope-recovery-v1.json"
)
SCOPE_RECOVERY_COOLDOWN = timedelta(minutes=15)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure the Memova Codex MCP server is OAuth-authenticated.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only report the current MCP auth state.",
    )
    parser.add_argument(
        "--reauthorize",
        action="store_true",
        help=(
            "Run OAuth even when Codex reports an existing Memova login."
        ),
    )
    parser.add_argument(
        "--recover-scopes",
        action="store_true",
        help=(
            "Run one cooldown-guarded OAuth recovery when the requested workflow reports "
            "missing scopes or tools."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Maximum seconds to wait for browser OAuth approval.",
    )
    parser.add_argument(
        "--workflow",
        choices=("all", "personal-manual"),
        default="all",
        help="Request only the scopes needed by one supported workflow.",
    )
    args = parser.parse_args()
    if args.check_only and (args.reauthorize or args.recover_scopes):
        parser.error("--check-only cannot be combined with OAuth recovery")
    if args.reauthorize and args.recover_scopes:
        parser.error("--reauthorize and --recover-scopes cannot be combined")

    requested_scopes = list(
        PERSONAL_MANUAL_SCOPES if args.workflow == "personal-manual" else BASE_SCOPES
    )
    login_command = build_login_command(requested_scopes)

    before = _mcp_status(login_command)
    if not before.get("listed"):
        _write_json({"status": "missing_mcp_server", "before": before})
        return 2

    recovery_state_path = scope_recovery_state_path()
    recovery_state = read_scope_recovery_state(recovery_state_path)
    if (
        args.recover_scopes
        and before.get("auth") == "OAuth"
        and recently_recovered_scopes(
            recovery_state,
            requested_scopes=requested_scopes,
            now=datetime.now(timezone.utc),
        )
    ):
        _write_json(
            {
                "status": "recent_scope_recovery_requires_client_refresh",
                "before": before,
                "after": before,
                "requested_scopes": requested_scopes,
                "scope_verification": "oauth_recently_completed_for_requested_scopes",
                "oauth_attempted": False,
                "restart_or_new_task_required": True,
                "manual_login_command": " ".join(login_command),
            }
        )
        return 0

    if before.get("auth") == "OAuth" and not (args.reauthorize or args.recover_scopes):
        _write_json(
            {
                "status": "already_logged_in",
                "before": before,
                "after": before,
                "requested_scopes": requested_scopes,
                "scope_verification": "unavailable_from_codex_mcp_list",
                "reauthorization_required_to_guarantee_scopes": True,
                "manual_login_command": " ".join(login_command),
            }
        )
        return 0
    if args.check_only:
        _write_json({"status": "not_logged_in", "before": before})
        return 1

    login = _run_login(
        login_command=login_command,
        timeout_seconds=max(1, args.timeout_seconds),
    )
    after = _mcp_status(login_command)
    login_completed = after.get("auth") == "OAuth" and login.get("login_returncode") == 0
    status = "login_completed" if login_completed else "login_incomplete"
    recovery_state_error = None
    if login_completed:
        try:
            write_scope_recovery_state(
                recovery_state_path,
                requested_scopes=requested_scopes,
                completed_at=datetime.now(timezone.utc),
            )
        except OSError as exc:
            recovery_state_error = f"{type(exc).__name__}: {exc}"
    _write_json(
        {
            "status": status,
            "before": before,
            "after": after,
            "requested_scopes": requested_scopes,
            "scope_verification": (
                "oauth_completed_for_requested_scopes" if login_completed else "not_verified"
            ),
            "oauth_attempted": True,
            "restart_or_new_task_required": login_completed,
            "scope_recovery_state_error": recovery_state_error,
            **login,
        }
    )
    return 0 if login_completed else 1


def build_login_command(scopes: list[str]) -> list[str]:
    normalized: list[str] = []
    for scope in scopes:
        value = str(scope).strip()
        if not SCOPE_RE.fullmatch(value):
            raise ValueError(f"Invalid MCP OAuth scope: {scope!r}")
        if value not in normalized:
            normalized.append(value)
    return [
        "codex",
        "mcp",
        "login",
        SERVER_NAME,
        "--scopes",
        ",".join(normalized),
    ]


def scope_recovery_state_path() -> Path:
    configured = os.getenv("MEMOVA_MCP_SCOPE_RECOVERY_STATE_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_SCOPE_RECOVERY_STATE_PATH


def read_scope_recovery_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def recently_recovered_scopes(
    state: dict[str, Any],
    *,
    requested_scopes: list[str],
    now: datetime,
) -> bool:
    if set(state.get("requested_scopes") or ()) != set(requested_scopes):
        return False
    completed_at = _parse_timestamp(state.get("completed_at"))
    if completed_at is None:
        return False
    age = now.astimezone(timezone.utc) - completed_at
    return timedelta(0) <= age < SCOPE_RECOVERY_COOLDOWN


def write_scope_recovery_state(
    path: Path,
    *,
    requested_scopes: list[str],
    completed_at: datetime,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "memova_oauth_scope_recovery_v1",
        "completed_at": _format_timestamp(completed_at),
        "requested_scopes": sorted(set(requested_scopes)),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mcp_status(login_command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["codex", "mcp", "list"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return {
            "listed": False,
            "auth": None,
            "returncode": None,
            "raw": "",
            "error": f"{type(exc).__name__}: {exc}",
            "manual_login_command": " ".join(login_command),
        }
    output = result.stdout or ""
    status: dict[str, Any] = {
        "listed": False,
        "auth": None,
        "returncode": result.returncode,
        "raw": output,
    }
    for line in output.splitlines():
        fields = line.split()
        if fields and fields[0] == SERVER_NAME:
            status["listed"] = True
            if "OAuth" in fields:
                status["auth"] = "OAuth"
            elif "Not" in fields and "logged" in fields and "in" in fields:
                status["auth"] = "Not logged in"
            else:
                status["auth"] = fields[-1] if fields else None
            break
    return status


def _run_login(*, login_command: list[str], timeout_seconds: int) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            login_command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return {
            "login_returncode": None,
            "opened_authorization_url": False,
            "timed_out": False,
            "login_error": f"{type(exc).__name__}: {exc}",
            "manual_login_command": " ".join(login_command),
            "recovery_hint": (
                "Run the manual_login_command in Windows Terminal/PowerShell or a normal shell, "
                "finish OAuth in the browser, then restart Codex or open a new thread."
            ),
        }
    assert process.stdout is not None
    output_queue: queue.Queue[str | None] = queue.Queue()
    output_lines: list[str] = []
    opened_url: str | None = None
    open_result: dict[str, Any] | None = None
    deadline = time.monotonic() + timeout_seconds

    def read_output() -> None:
        try:
            for line in process.stdout:
                output_queue.put(line)
        finally:
            output_queue.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    output_done = False

    while process.poll() is None or not output_done:
        try:
            line = output_queue.get(timeout=0.2)
        except queue.Empty:
            line = ""
        if line is None:
            output_done = True
        elif line:
            output_lines.append(line)
            if opened_url is None:
                opened_url = _extract_authorization_url(line)
                if opened_url:
                    _show_copyable_url(opened_url)
                    open_result = _open_url(opened_url)
        if time.monotonic() > deadline:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            reader.join(timeout=1)
            output_lines.extend(_drain_output_queue(output_queue))
            return {
                "login_returncode": process.returncode,
                "opened_authorization_url": opened_url is not None,
                "authorization_url": opened_url,
                "browser_open": open_result if opened_url is not None else None,
                "timed_out": True,
                "login_output_tail": _tail(output_lines),
            }

    reader.join(timeout=1)
    for line in _drain_output_queue(output_queue):
        output_lines.append(line)
        if opened_url is None:
            opened_url = _extract_authorization_url(line)
            if opened_url:
                _show_copyable_url(opened_url)
                open_result = _open_url(opened_url)

    return {
        "login_returncode": process.returncode,
        "opened_authorization_url": opened_url is not None,
        "authorization_url": opened_url,
        "browser_open": open_result if opened_url is not None else None,
        "timed_out": False,
        "login_output_tail": _tail(output_lines),
    }


def _drain_output_queue(output_queue: queue.Queue[str | None]) -> list[str]:
    drained: list[str] = []
    while True:
        try:
            item = output_queue.get_nowait()
        except queue.Empty:
            break
        if item:
            drained.append(item)
    return drained


def _extract_authorization_url(text: str) -> str | None:
    match = AUTHORIZE_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,]")


def _show_copyable_url(url: str) -> None:
    print(
        "\nMemova OAuth authorization URL. If the browser does not open automatically, "
        "copy this URL into your browser:\n"
        f"{url}\n",
        file=sys.stderr,
        flush=True,
    )


def _open_url(url: str) -> dict[str, Any]:
    if webbrowser.open(url, new=2):
        return {"opened": True, "method": "python_webbrowser"}

    platform = sys.platform
    commands: list[list[str]] = []
    if platform == "darwin":
        commands.append(["open", url])
    elif platform.startswith("linux"):
        commands.append(["xdg-open", url])

    if platform.startswith("win"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return {"opened": True, "method": "os.startfile"}
        except (AttributeError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        commands.append(["cmd", "/c", "start", "", url])
    else:
        last_error = None

    for command in commands:
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        if result.returncode == 0:
            return {"opened": True, "method": command[0]}
        last_error = f"{command[0]} exited with {result.returncode}"

    return {
        "opened": False,
        "method": None,
        "error": last_error,
        "copy_url_manually": True,
    }


def _tail(lines: list[str], *, max_chars: int = 4000) -> str:
    text = "".join(lines)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
