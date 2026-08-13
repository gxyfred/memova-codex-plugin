#!/usr/bin/env python3
"""Install and manage the user-scoped Memova Collector runtime and scheduler."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
BUNDLED_COLLECTOR = PLUGIN_ROOT / "collector"
sys.path.insert(0, str(BUNDLED_COLLECTOR))

from memova_collector.contracts import COLLECTOR_VERSION, CONSENT_SCHEMA_VERSION  # noqa: E402
from memova_collector.ledger import inspect_ledger  # noqa: E402
from memova_collector.oauth import CollectorOAuthClient  # noqa: E402
from memova_collector.scheduler import (  # noqa: E402
    DEFAULT_INTERVAL_SECONDS,
    build_scheduler_plan,
    normalize_system,
)

MIN_PYTHON = (3, 11)


def _runtime_dependency_report() -> dict[str, Any]:
    return {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "minimum_python_version": ".".join(str(item) for item in MIN_PYTHON),
        "python_supported": sys.version_info >= MIN_PYTHON,
        "python_runtime_bundled": False,
        "scheduler_uses_current_python": True,
        "codex_app_server_required_for_live_collection": True,
    }


def _require_supported_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise RuntimeError(
            "Memova Collector 1.3.0 requires Python 3.11 or newer. "
            f"Current interpreter: {platform.python_version()} ({sys.executable})."
        )


def _platform_name(requested: str | None = None) -> str:
    if requested:
        return normalize_system(requested)
    if os.name == "nt":
        return "windows"
    return normalize_system(platform.system())


def default_install_root() -> Path:
    system = _platform_name()
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "Memova" / "CodexCollector"
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "Memova" / "CodexCollector"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "memova" / "codex-collector"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def _atomic_text(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    try:
        temporary.chmod(0o700 if executable else 0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in (BUNDLED_COLLECTOR / "memova_collector", BUNDLED_COLLECTOR / "schemas"):
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    return sorted(files)


def _bundle_manifest() -> dict[str, Any]:
    return {
        "schema_version": "memova_collector_runtime_manifest_v1",
        "collector_version": COLLECTOR_VERSION,
        "source": "memova-codex-plugin",
        "files": {
            str(path.relative_to(BUNDLED_COLLECTOR)): _hash_file(path) for path in _source_files()
        },
    }


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    install_root = Path(args.install_root).expanduser()
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else install_root / "state"
    version_root = install_root / "versions" / COLLECTOR_VERSION
    return {
        "install_root": install_root,
        "state_dir": state_dir,
        "version_root": version_root,
        "launcher": install_root / "bin" / "memova_collector_launcher.py",
        "current": install_root / "current.json",
        "scheduler_state": install_root / "scheduler.json",
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _launcher_content(version_root: Path) -> str:
    return "\n".join(
        [
            f"#!{sys.executable}",
            "from __future__ import annotations",
            "import sys",
            f"sys.path.insert(0, {str(version_root)!r})",
            "from memova_collector.cli import main",
            "raise SystemExit(main())",
            "",
        ],
    )


def _installed_manifest(paths: dict[str, Path]) -> dict[str, Any] | None:
    return _read_json(paths["version_root"] / "manifest.json")


def _runtime_is_current(paths: dict[str, Path], expected: dict[str, Any]) -> bool:
    current = _read_json(paths["current"])
    return bool(
        _installed_manifest(paths) == expected
        and paths["launcher"].is_file()
        and current
        and current.get("collector_version") == COLLECTOR_VERSION
        and current.get("runtime") == str(paths["version_root"])
        and current.get("launcher") == str(paths["launcher"])
    )


def _readiness(
    paths: dict[str, Path],
    api_base: str = "https://api.memova.ai",
) -> dict[str, Any]:
    consent = _read_json(paths["state_dir"] / "consent.json")
    snapshot = inspect_ledger(paths["state_dir"] / "collector.sqlite3")
    metadata = snapshot.get("metadata", {}) if snapshot else {}
    preview_source = metadata.get("preview_source")
    try:
        oauth_status = CollectorOAuthClient(api_base).status()
    except RuntimeError as exc:
        oauth_status = {"connected": False, "error": str(exc)}
    return {
        "consent_active": bool(
            consent
            and consent.get("schema_version") == CONSENT_SCHEMA_VERSION
            and consent.get("status") == "active"
        ),
        "live_preview_completed": bool(
            preview_source == "live" and metadata.get("preview_completed_at")
        ),
        "preview_source": preview_source,
        "oauth_connected": bool(oauth_status.get("connected")),
        "oauth": oauth_status,
    }


def _scheduler_plan(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    system = _platform_name(args.platform)
    home = Path(args.home).expanduser() if args.home else Path.home()
    return build_scheduler_plan(
        system=system,
        home=home,
        state_dir=paths["state_dir"],
        python_executable=sys.executable,
        launcher=paths["launcher"],
        interval_seconds=args.interval_seconds,
        api_base=args.api_base,
    )


def _verified_scheduler_plan(
    state: dict[str, Any],
    paths: dict[str, Path],
) -> dict[str, Any]:
    plan = build_scheduler_plan(
        system=str(state.get("platform") or ""),
        home=Path(str(state.get("home") or Path.home())),
        state_dir=paths["state_dir"],
        python_executable=sys.executable,
        launcher=paths["launcher"],
        interval_seconds=int(state.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS),
        api_base=str(state.get("api_base") or "https://api.memova.ai"),
    )
    if sorted(plan["files"]) != sorted(state.get("files") or []):
        raise RuntimeError("Scheduler state paths do not match a fresh trusted plan.")
    if plan["activation_commands"] != state.get("activation_commands"):
        raise RuntimeError("Scheduler activation commands do not match a fresh trusted plan.")
    if plan["deactivation_commands"] != state.get("deactivation_commands"):
        raise RuntimeError("Scheduler deactivation commands do not match a fresh trusted plan.")
    return plan


def command_plan(args: argparse.Namespace) -> int:
    paths = _paths(args)
    bundled = _bundle_manifest()
    installed = _installed_manifest(paths)
    scheduler = _read_json(paths["scheduler_state"])
    _print_json(
        {
            "status": "plan",
            "collector_version": COLLECTOR_VERSION,
            "source_fingerprint": hashlib.sha256(
                json.dumps(bundled, sort_keys=True).encode("utf-8"),
            ).hexdigest(),
            "install_root": str(paths["install_root"]),
            "state_dir": str(paths["state_dir"]),
            "runtime_installed": _runtime_is_current(paths, bundled),
            "installed_version": installed.get("collector_version") if installed else None,
            "scheduler_definition_written": scheduler is not None,
            "scheduler_active": bool(scheduler and scheduler.get("active")),
            "readiness": _readiness(paths),
            "runtime_dependencies": _runtime_dependency_report(),
            "remote_upload_enabled": False,
            "next_action": (
                "none" if _runtime_is_current(paths, bundled) else "install_or_update_runtime"
            ),
        },
    )
    return 0


def command_install(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise RuntimeError("Runtime installation requires --confirm after reviewing plan.")
    paths = _paths(args)
    expected = _bundle_manifest()
    existing = _installed_manifest(paths)
    if existing is not None and existing != expected:
        raise RuntimeError(
            "The installed directory contains different bytes for the same version. "
            "Refusing an in-place overwrite; publish a new version instead.",
        )
    changed = existing is None
    if changed:
        staging = paths["version_root"].with_name(
            f".{COLLECTOR_VERSION}.{uuid.uuid4().hex}.staging",
        )
        staging.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(
                BUNDLED_COLLECTOR / "memova_collector",
                staging / "memova_collector",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            shutil.copytree(BUNDLED_COLLECTOR / "schemas", staging / "schemas")
            _atomic_json(staging / "manifest.json", expected)
            os.replace(staging, paths["version_root"])
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    _atomic_text(paths["launcher"], _launcher_content(paths["version_root"]), executable=True)
    _atomic_json(
        paths["current"],
        {
            "collector_version": COLLECTOR_VERSION,
            "runtime": str(paths["version_root"]),
            "launcher": str(paths["launcher"]),
        },
    )
    _print_json(
        {
            "status": "installed" if changed else "already_current",
            "collector_version": COLLECTOR_VERSION,
            "install_root": str(paths["install_root"]),
            "launcher": str(paths["launcher"]),
            "state_dir": str(paths["state_dir"]),
            "scheduler_installed": _read_json(paths["scheduler_state"]) is not None,
            "remote_upload_enabled": False,
        },
    )
    return 0


def command_scheduler_plan(args: argparse.Namespace) -> int:
    paths = _paths(args)
    if not _runtime_is_current(paths, _bundle_manifest()):
        raise RuntimeError("Install the current Collector runtime before planning its scheduler.")
    plan = _scheduler_plan(args, paths)
    readiness = _readiness(paths, args.api_base)
    plan["readiness"] = readiness
    plan["ready_to_write"] = all(
        (
            readiness["consent_active"],
            readiness["live_preview_completed"],
            readiness["oauth_connected"],
        )
    )
    plan["file_paths"] = sorted(plan.pop("files"))
    _print_json({"status": "scheduler_plan", **plan})
    return 0


def command_write_scheduler(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise RuntimeError("Scheduler definition changes require --confirm after reviewing plan.")
    paths = _paths(args)
    if not _runtime_is_current(paths, _bundle_manifest()):
        raise RuntimeError("Install the current Collector runtime before writing its scheduler.")
    readiness = _readiness(paths, args.api_base)
    if not all(
        (
            readiness["consent_active"],
            readiness["live_preview_completed"],
            readiness["oauth_connected"],
        )
    ):
        raise RuntimeError(
            "Scheduler requires active consent, a recorded live preview, and Memova OAuth.",
        )
    plan = _scheduler_plan(args, paths)
    (paths["state_dir"] / "logs").mkdir(parents=True, exist_ok=True)
    for raw_path, content in plan["files"].items():
        target = Path(raw_path)
        if target.exists() and target.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite a different scheduler file: {target}")
        _atomic_text(target, content)
    scheduler_state = {
        "schema_version": "memova_collector_scheduler_state_v1",
        "platform": plan["platform"],
        "home": str(Path(args.home).expanduser() if args.home else Path.home()),
        "interval_seconds": plan["interval_seconds"],
        "api_base": args.api_base.rstrip("/"),
        "files": sorted(plan["files"]),
        "file_hashes": {
            path: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for path, content in plan["files"].items()
        },
        "activation_commands": plan["activation_commands"],
        "deactivation_commands": plan["deactivation_commands"],
        "active": False,
        "remote_upload_enabled": True,
    }
    _atomic_json(paths["scheduler_state"], scheduler_state)
    _print_json(
        {
            "status": "scheduler_definition_written_not_activated",
            **scheduler_state,
            "scheduler_state": str(paths["scheduler_state"]),
        },
    )
    return 0


def _run_commands(commands: list[list[str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            },
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Scheduler command failed: {command}")
    return results


def command_activate_scheduler(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise RuntimeError("Scheduler activation requires --confirm after reviewing exact commands.")
    paths = _paths(args)
    state = _read_json(paths["scheduler_state"])
    if state is None:
        raise RuntimeError("Write the scheduler definition before activation.")
    if state.get("platform") != _platform_name():
        raise RuntimeError("Refusing to activate a scheduler definition for another operating system.")
    plan = _verified_scheduler_plan(state, paths)
    results = _run_commands(plan["activation_commands"])
    state["active"] = True
    state["activated_at_epoch"] = time.time()
    _atomic_json(paths["scheduler_state"], state)
    _print_json({"status": "scheduler_active", "commands": results})
    return 0


def command_deactivate_scheduler(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise RuntimeError("Scheduler deactivation requires --confirm.")
    paths = _paths(args)
    state = _read_json(paths["scheduler_state"])
    if state is None:
        _print_json({"status": "scheduler_not_configured"})
        return 0
    if state.get("active"):
        if state.get("platform") != _platform_name():
            raise RuntimeError("Refusing to deactivate a scheduler for another operating system.")
        plan = _verified_scheduler_plan(state, paths)
        _run_commands(plan["deactivation_commands"])
    state["active"] = False
    state["deactivated_at_epoch"] = time.time()
    _atomic_json(paths["scheduler_state"], state)
    _print_json({"status": "scheduler_inactive", "definition_files_retained": True})
    return 0


def command_remove_scheduler(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise RuntimeError("Removing scheduler definitions requires --confirm.")
    paths = _paths(args)
    state = _read_json(paths["scheduler_state"])
    if state is None:
        _print_json({"status": "scheduler_not_configured"})
        return 0
    if state.get("active"):
        raise RuntimeError("Deactivate the scheduler before removing its definition files.")
    plan = _verified_scheduler_plan(state, paths)
    expected_hashes = state.get("file_hashes") or {}
    removed: list[str] = []
    for raw_path in sorted(plan["files"]):
        target = Path(raw_path)
        if not target.exists():
            continue
        actual_hash = _hash_file(target)
        if actual_hash != expected_hashes.get(raw_path):
            raise RuntimeError(f"Refusing to remove a changed scheduler file: {target}")
        target.unlink()
        removed.append(str(target))
    paths["scheduler_state"].unlink()
    _print_json({"status": "scheduler_definitions_removed", "removed": removed})
    return 0


def command_uninstall(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise RuntimeError("Collector uninstall requires --confirm after reviewing plan.")
    paths = _paths(args)
    scheduler = _read_json(paths["scheduler_state"])
    if scheduler is not None:
        raise RuntimeError(
            "Deactivate and remove scheduler definitions before uninstalling the runtime.",
        )
    if not paths["install_root"].exists():
        _print_json({"status": "not_installed"})
        return 0
    removed = paths["install_root"].with_name(
        f"{paths['install_root'].name}.removed-{int(time.time())}-{uuid.uuid4().hex[:8]}",
    )
    os.replace(paths["install_root"], removed)
    _print_json(
        {
            "status": "uninstalled_to_recoverable_archive",
            "archive": str(removed),
            "local_history_deleted": False,
            "remote_delete_requested": False,
        },
    )
    return 0


def _add_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--install-root", default=str(default_install_root()))
    parser.add_argument("--state-dir")


def _add_scheduler_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform")
    parser.add_argument("--home")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--api-base", default="https://api.memova.ai")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage_conversation_sync.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    _add_paths(plan)
    plan.set_defaults(handler=command_plan)

    install = subparsers.add_parser("install")
    _add_paths(install)
    install.add_argument("--confirm", action="store_true")
    install.set_defaults(handler=command_install)

    scheduler_plan = subparsers.add_parser("scheduler-plan")
    _add_paths(scheduler_plan)
    _add_scheduler_options(scheduler_plan)
    scheduler_plan.set_defaults(handler=command_scheduler_plan)

    write_scheduler = subparsers.add_parser("write-scheduler")
    _add_paths(write_scheduler)
    _add_scheduler_options(write_scheduler)
    write_scheduler.add_argument("--confirm", action="store_true")
    write_scheduler.set_defaults(handler=command_write_scheduler)

    activate = subparsers.add_parser("activate-scheduler")
    _add_paths(activate)
    activate.add_argument("--confirm", action="store_true")
    activate.set_defaults(handler=command_activate_scheduler)

    deactivate = subparsers.add_parser("deactivate-scheduler")
    _add_paths(deactivate)
    deactivate.add_argument("--confirm", action="store_true")
    deactivate.set_defaults(handler=command_deactivate_scheduler)

    remove_scheduler = subparsers.add_parser("remove-scheduler")
    _add_paths(remove_scheduler)
    remove_scheduler.add_argument("--confirm", action="store_true")
    remove_scheduler.set_defaults(handler=command_remove_scheduler)

    uninstall = subparsers.add_parser("uninstall")
    _add_paths(uninstall)
    uninstall.add_argument("--confirm", action="store_true")
    uninstall.set_defaults(handler=command_uninstall)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_supported_python()
        return int(args.handler(args))
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
