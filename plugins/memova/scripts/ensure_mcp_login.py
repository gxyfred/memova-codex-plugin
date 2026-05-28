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
from typing import Any

SERVER_NAME = "memova"
SCOPES = "notes.read,actions.read,actions.write,automation.read,automation.write"
AUTHORIZE_URL_RE = re.compile(r"https://\S+")
LOGIN_COMMAND = ["codex", "mcp", "login", SERVER_NAME, "--scopes", SCOPES]


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
        "--timeout-seconds",
        type=int,
        default=300,
        help="Maximum seconds to wait for browser OAuth approval.",
    )
    args = parser.parse_args()

    before = _mcp_status()
    if before.get("auth") == "OAuth":
        _write_json({"status": "already_logged_in", "before": before, "after": before})
        return 0
    if not before.get("listed"):
        _write_json({"status": "missing_mcp_server", "before": before})
        return 2
    if args.check_only:
        _write_json({"status": "not_logged_in", "before": before})
        return 1

    login = _run_login(timeout_seconds=max(1, args.timeout_seconds))
    after = _mcp_status()
    status = "login_completed" if after.get("auth") == "OAuth" else "login_incomplete"
    _write_json({"status": status, "before": before, "after": after, **login})
    return 0 if status == "login_completed" else 1


def _mcp_status() -> dict[str, Any]:
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
            "manual_login_command": " ".join(LOGIN_COMMAND),
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


def _run_login(*, timeout_seconds: int) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            LOGIN_COMMAND,
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
            "manual_login_command": " ".join(LOGIN_COMMAND),
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
