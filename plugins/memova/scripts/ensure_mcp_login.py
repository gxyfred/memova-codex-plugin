#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import selectors
import subprocess
import sys
import time
from typing import Any

SERVER_NAME = "memova"
SCOPES = "notes.read,actions.read,actions.write,automation.read,automation.write"
AUTHORIZE_URL_RE = re.compile(r"https://\S+")


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
    result = subprocess.run(
        ["codex", "mcp", "list"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
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
    process = subprocess.Popen(
        ["codex", "mcp", "login", SERVER_NAME, "--scopes", SCOPES],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output_lines: list[str] = []
    opened_url = None
    deadline = time.monotonic() + timeout_seconds

    while process.poll() is None:
        events = selector.select(timeout=0.2)
        if events:
            line = process.stdout.readline()
            if not line:
                continue
            output_lines.append(line)
            if opened_url is None:
                match = AUTHORIZE_URL_RE.search(line)
                if match:
                    opened_url = match.group(0)
                    _open_url(opened_url)
        if time.monotonic() > deadline:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            selector.close()
            return {
                "login_returncode": process.returncode,
                "opened_authorization_url": opened_url is not None,
                "timed_out": True,
                "login_output_tail": _tail(output_lines),
            }

    remainder = process.stdout.read()
    selector.close()
    if remainder:
        output_lines.append(remainder)
        if opened_url is None:
            match = AUTHORIZE_URL_RE.search(remainder)
            if match:
                opened_url = match.group(0)
                _open_url(opened_url)

    return {
        "login_returncode": process.returncode,
        "opened_authorization_url": opened_url is not None,
        "timed_out": False,
        "login_output_tail": _tail(output_lines),
    }


def _open_url(url: str) -> None:
    subprocess.run(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _tail(lines: list[str], *, max_chars: int = 4000) -> str:
    text = "".join(lines)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
