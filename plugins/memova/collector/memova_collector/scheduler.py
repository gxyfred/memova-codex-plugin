from __future__ import annotations

import os
import plistlib
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SCHEDULER_ID = "ai.memova.codex-conversation-collector"
WINDOWS_TASK_NAME = "Memova Codex Conversation Collector"
MINIMUM_INTERVAL_SECONDS = 300
DEFAULT_INTERVAL_SECONDS = 900


def normalize_system(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "darwin": "darwin",
        "mac": "darwin",
        "macos": "darwin",
        "linux": "linux",
        "windows": "windows",
        "win32": "windows",
        "nt": "windows",
    }
    if normalized not in aliases:
        raise ValueError(f"Unsupported scheduler platform: {value}")
    return aliases[normalized]


def collector_arguments(
    *,
    python_executable: str | Path,
    launcher: str | Path,
    state_dir: str | Path,
    api_base: str = "https://api.memova.ai",
) -> list[str]:
    return [
        str(python_executable),
        str(launcher),
        "sync-once",
        "--state-dir",
        str(Path(state_dir)),
        "--live",
        "--allow-experimental-app-server",
        "--sink",
        "rest",
        "--api-base",
        api_base.rstrip("/"),
    ]


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'


def _launchd_plan(
    *,
    home: Path,
    state_dir: Path,
    arguments: list[str],
    interval_seconds: int,
) -> dict[str, Any]:
    target = home / "Library" / "LaunchAgents" / f"{SCHEDULER_ID}.plist"
    logs = state_dir / "logs"
    content = plistlib.dumps(
        {
            "Label": SCHEDULER_ID,
            "ProgramArguments": arguments,
            "RunAtLoad": True,
            "StartInterval": interval_seconds,
            "ProcessType": "Background",
            "ThrottleInterval": 60,
            "StandardOutPath": str(logs / "collector.stdout.log"),
            "StandardErrorPath": str(logs / "collector.stderr.log"),
        },
        sort_keys=True,
    ).decode("utf-8")
    domain = f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui/$UID"
    return {
        "files": {str(target): content},
        "activation_commands": [["launchctl", "bootstrap", domain, str(target)]],
        "deactivation_commands": [["launchctl", "bootout", domain, str(target)]],
    }


def _systemd_plan(
    *,
    home: Path,
    arguments: list[str],
    interval_seconds: int,
) -> dict[str, Any]:
    unit_dir = home / ".config" / "systemd" / "user"
    service_name = "memova-codex-conversation-collector.service"
    timer_name = "memova-codex-conversation-collector.timer"
    service_path = unit_dir / service_name
    timer_path = unit_dir / timer_name
    exec_start = " ".join(_systemd_quote(argument) for argument in arguments)
    service = "\n".join(
        [
            "[Unit]",
            "Description=Memova Codex conversation Collector",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={exec_start}",
            "",
        ],
    )
    timer = "\n".join(
        [
            "[Unit]",
            "Description=Run the Memova Codex conversation Collector periodically",
            "",
            "[Timer]",
            "OnBootSec=2m",
            f"OnUnitActiveSec={interval_seconds}s",
            "RandomizedDelaySec=60s",
            "Persistent=true",
            "Unit=memova-codex-conversation-collector.service",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ],
    )
    return {
        "files": {str(service_path): service, str(timer_path): timer},
        "activation_commands": [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", timer_name],
        ],
        "deactivation_commands": [
            ["systemctl", "--user", "disable", "--now", timer_name],
            ["systemctl", "--user", "daemon-reload"],
        ],
    }


def _windows_plan(
    *,
    home: Path,
    state_dir: Path,
    arguments: list[str],
    interval_seconds: int,
) -> dict[str, Any]:
    task_path = state_dir / "scheduler" / f"{SCHEDULER_ID}.xml"
    namespace = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", namespace)

    def element(parent: ET.Element, name: str, text: str | None = None) -> ET.Element:
        child = ET.SubElement(parent, f"{{{namespace}}}{name}")
        child.text = text
        return child

    task = ET.Element(f"{{{namespace}}}Task", {"version": "1.4"})
    registration = element(task, "RegistrationInfo")
    element(registration, "Description", "Memova Codex conversation Collector")
    triggers = element(task, "Triggers")
    time_trigger = element(triggers, "TimeTrigger")
    element(time_trigger, "StartBoundary", "2026-01-01T00:00:00")
    repetition = element(time_trigger, "Repetition")
    minutes = max(5, interval_seconds // 60)
    element(repetition, "Interval", f"PT{minutes}M")
    element(repetition, "Duration", "P3650D")
    element(repetition, "StopAtDurationEnd", "false")
    element(time_trigger, "Enabled", "true")
    principals = element(task, "Principals")
    principal = ET.SubElement(principals, f"{{{namespace}}}Principal", {"id": "Author"})
    element(principal, "LogonType", "InteractiveToken")
    element(principal, "RunLevel", "LeastPrivilege")
    settings = element(task, "Settings")
    element(settings, "MultipleInstancesPolicy", "IgnoreNew")
    element(settings, "StartWhenAvailable", "true")
    element(settings, "ExecutionTimeLimit", "PT1H")
    element(settings, "Enabled", "true")
    actions = element(task, "Actions")
    actions.set("Context", "Author")
    execute = element(actions, "Exec")
    element(execute, "Command", arguments[0])
    element(execute, "Arguments", subprocess.list2cmdline(arguments[1:]))
    element(execute, "WorkingDirectory", str(home))
    content = ET.tostring(task, encoding="unicode", xml_declaration=True)
    return {
        "files": {str(task_path): content},
        "activation_commands": [
            ["schtasks", "/Create", "/TN", WINDOWS_TASK_NAME, "/XML", str(task_path), "/F"],
        ],
        "deactivation_commands": [
            ["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
        ],
    }


def build_scheduler_plan(
    *,
    system: str,
    home: str | Path,
    state_dir: str | Path,
    python_executable: str | Path,
    launcher: str | Path,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    api_base: str = "https://api.memova.ai",
) -> dict[str, Any]:
    system = normalize_system(system)
    if interval_seconds < MINIMUM_INTERVAL_SECONDS:
        raise ValueError(
            f"Scheduler interval must be at least {MINIMUM_INTERVAL_SECONDS} seconds.",
        )
    home_path = Path(home)
    state_path = Path(state_dir)
    arguments = collector_arguments(
        python_executable=python_executable,
        launcher=launcher,
        state_dir=state_path,
        api_base=api_base,
    )
    if system == "darwin":
        platform_plan = _launchd_plan(
            home=home_path,
            state_dir=state_path,
            arguments=arguments,
            interval_seconds=interval_seconds,
        )
    elif system == "linux":
        platform_plan = _systemd_plan(
            home=home_path,
            arguments=arguments,
            interval_seconds=interval_seconds,
        )
    else:
        platform_plan = _windows_plan(
            home=home_path,
            state_dir=state_path,
            arguments=arguments,
            interval_seconds=interval_seconds,
        )
    return {
        "scheduler_id": SCHEDULER_ID,
        "platform": system,
        "interval_seconds": interval_seconds,
        "collector_arguments": arguments,
        "sink": "memova-rest",
        "remote_upload_enabled": True,
        **platform_plan,
    }
