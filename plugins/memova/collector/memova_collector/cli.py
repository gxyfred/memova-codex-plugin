from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .app_server import JsonRpcAppServerClient, ThreadSource
from .capability import inspect_capabilities
from .contracts import (
    CONSENT_SCHEMA_VERSION,
    STATUS_SCHEMA_VERSION,
    build_consent_record,
    default_collection_policy,
    utc_now,
)
from .fixtures import FixtureThreadSource
from .ledger import Ledger, inspect_ledger
from .knowledge_v5 import (
    CodexKnowledgeV5Runner,
    KnowledgeV5AnalyzerLoop,
    KnowledgeV5ApiClient,
    analyzer_workspace_root,
)
from .locking import RunLock, read_lock
from .oauth import CollectorOAuthClient
from .sinks import MockSink, RestSink
from .sync import SyncEngine


def default_state_dir() -> Path:
    if platform.system() == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Memova"
            / "CodexCollector"
            / "state"
        )
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return root / "Memova" / "CodexCollector" / "state"
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "memova" / "codex-collector" / "state"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _state_dir(args: argparse.Namespace) -> Path:
    return Path(args.state_dir).expanduser()


def _ledger_path(args: argparse.Namespace) -> Path:
    return _state_dir(args) / "collector.sqlite3"


def _oauth(args: argparse.Namespace) -> CollectorOAuthClient:
    return CollectorOAuthClient(str(args.api_base))


def _load_consent(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "consent.json"
    if not path.exists():
        raise RuntimeError("Collector setup is incomplete. Run setup with --accept-policy first.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONSENT_SCHEMA_VERSION:
        raise RuntimeError("Collector consent contract is unsupported; setup must be repeated.")
    if payload.get("status") != "active":
        raise RuntimeError("Collector consent is not active.")
    return payload


def _live_source(args: argparse.Namespace) -> JsonRpcAppServerClient:
    report = inspect_capabilities(args.codex_path)
    if not report["supported"]:
        raise RuntimeError(f"Codex App Server capability gate failed: {report['reasons']}")
    if report["experimental"] and not args.allow_experimental_app_server:
        raise RuntimeError(
            "Codex App Server is experimental. Re-run with --allow-experimental-app-server "
            "only for an explicitly approved local preview.",
        )
    return JsonRpcAppServerClient(args.codex_path)


def _source(args: argparse.Namespace) -> tuple[ThreadSource, bool]:
    if args.fixture:
        return FixtureThreadSource(args.fixture), False
    if not args.live:
        raise RuntimeError("Choose exactly one source: --fixture PATH or --live.")
    return _live_source(args), True


def command_capabilities(args: argparse.Namespace) -> int:
    report = inspect_capabilities(args.codex_path)
    _print_json(report)
    return 0 if report["supported"] else 2


def command_policy(_: argparse.Namespace) -> int:
    _print_json(default_collection_policy())
    return 0


def _requested_project_context_mode(args: argparse.Namespace) -> str:
    if bool(getattr(args, "disable_project_context", False)):
        return "disabled"
    if bool(getattr(args, "include_project_context", False)):
        return "full"
    return "minimal"


def command_setup(args: argparse.Namespace) -> int:
    project_context_mode = _requested_project_context_mode(args)
    if not args.accept_policy:
        _print_json(
            {
                "status": "consent_required",
                "message": "Review `policy`, then repeat setup with --accept-policy.",
                "archive_notice": (
                    "Enabling sync archives complete visible Codex history in Memova until "
                    "you delete a thread, this device's archive, all Codex data, or your "
                    "Memova account. Pause, disconnect, and uninstall do not delete it."
                ),
                "project_context_notice": (
                    "Fresh setup includes a privacy-minimal repository fingerprint by default so "
                    "Memova can group tasks from the same repository. --include-project-context "
                    "also sends its display name, branch, and repository-relative working path. "
                    "Neither mode sends the HMAC key, absolute cwd, remote URL, credentials, "
                    "query string, or commit SHA. --disable-project-context sends no repository "
                    "context."
                ),
                "project_context_mode": project_context_mode,
                "policy": default_collection_policy(
                    project_context_mode=project_context_mode,
                ),
            },
        )
        return 2
    state_dir = _state_dir(args)
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        state_dir.chmod(0o700)
    except OSError:
        pass
    consent = build_consent_record(
        consent_id=args.consent_id or f"consent-{uuid.uuid4()}",
        device_id=args.device_id or f"device-{uuid.uuid4()}",
        memova_account_hint=args.memova_account_hint,
        project_context_mode=project_context_mode,
    )
    (state_dir / "consent.json").write_text(
        json.dumps(consent, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        (state_dir / "consent.json").chmod(0o600)
    except OSError:
        pass
    with Ledger(_ledger_path(args)) as ledger:
        ledger.set_metadata("consent_id", consent["consent_id"])
        ledger.set_metadata("device_id", consent["device_id"])
        ledger.set_metadata("paused", "false")
        ledger.set_metadata("mode", "v5_ready_not_connected")
        ledger.set_metadata("knowledge_mode", "knowledge_v5")
        ledger.set_metadata(
            "project_context_enabled",
            "true" if project_context_mode != "disabled" else "false",
        )
        ledger.set_metadata("project_context_mode", project_context_mode)
    _print_json(
        {
            "status": "configured_for_v5",
            "knowledge_mode": "knowledge_v5",
            "state_dir": str(state_dir),
            "consent_id": consent["consent_id"],
            "device_id": consent["device_id"],
            "oauth_configured": False,
            "scheduler_installed": False,
            "hooks_bundled": True,
            "hooks_trusted": None,
            "remote_upload_enabled": False,
            "retention_mode": "until_user_or_account_deletion",
            "project_context_enabled": project_context_mode != "disabled",
            "project_context_mode": project_context_mode,
            "next_action": "preview_then_connect",
        },
    )
    return 0


def _run_sync(
    *,
    args: argparse.Namespace,
    source: ThreadSource,
    ledger: Ledger,
    consent: dict[str, Any],
) -> dict[str, Any]:
    if args.sink == "mock":
        output = args.output or str(_state_dir(args) / "mock-batches.jsonl")
        sink = MockSink(output)
        ledger.set_metadata("mode", "mock")
    else:
        sink = RestSink(api_base=args.api_base, oauth=_oauth(args), consent=consent)
        ledger.set_metadata("mode", "rest")
    return SyncEngine(
        source=source,
        ledger=ledger,
        sink=sink,
        consent_id=str(consent["consent_id"]),
        device_id=str(consent["device_id"]),
        thread_ids=set(args.thread_id or []),
        excluded_cwd_roots=(str(analyzer_workspace_root(_state_dir(args))),),
    ).run_once()


def _run_knowledge_v5(
    *,
    args: argparse.Namespace,
    ledger: Ledger,
    consent: dict[str, Any],
    archived_result: dict[str, Any],
) -> dict[str, Any]:
    if bool(getattr(args, "skip_knowledge_v5", False)):
        return {"status": "disabled_for_this_run"}
    oauth = _oauth(args)
    loop = KnowledgeV5AnalyzerLoop(
        client=KnowledgeV5ApiClient(api_base=args.api_base, oauth=oauth),
        runner=CodexKnowledgeV5Runner(
            state_dir=_state_dir(args),
            codex_path=args.codex_path,
        ),
        ledger=ledger,
        state_dir=_state_dir(args),
        device_id=str(consent["device_id"]),
    )
    trigger = bool(
        archived_result.get("acknowledged_batch_count", 0)
        or ledger.get_metadata("knowledge_v5_initialized") != "true"
        or ledger.get_metadata("knowledge_v5_retry_required") == "true"
        or loop.has_pending_run()
    )
    return loop.run_once(trigger=trigger)


def command_sync_once(args: argparse.Namespace) -> int:
    snapshot = inspect_ledger(_ledger_path(args))
    if snapshot is not None and snapshot["paused"]:
        _print_json(
            {
                "status": "paused",
                "listed_thread_count": 0,
                "read_thread_count": 0,
                "staged_batch_count": 0,
                "acknowledged_batch_count": 0,
                "remote_upload_performed": False,
            },
        )
        return 0
    consent = _load_consent(_state_dir(args))
    with RunLock(_state_dir(args) / "sync.lock"):
        source, should_close = _source(args)
        try:
            with Ledger(_ledger_path(args)) as ledger:
                result = _run_sync(args=args, source=source, ledger=ledger, consent=consent)
                result["remote_upload_performed"] = bool(
                    args.sink == "rest" and result.get("acknowledged_batch_count", 0)
                )
                result["sink"] = args.sink
                if args.sink == "rest":
                    result["knowledge_v5"] = _run_knowledge_v5(
                        args=args,
                        ledger=ledger,
                        consent=consent,
                        archived_result=result,
                    )
                result["ledger"] = ledger.status()
                if args.sink == "mock":
                    result["output"] = args.output or str(
                        _state_dir(args) / "mock-batches.jsonl",
                    )
            _print_json(result)
            return 0
        finally:
            if should_close and isinstance(source, JsonRpcAppServerClient):
                source.close()


def command_preview(args: argparse.Namespace) -> int:
    if args.live and not args.acknowledge_local_read:
        raise RuntimeError("Live preview requires --acknowledge-local-read.")
    source, should_close = _source(args)
    try:
        with tempfile.TemporaryDirectory(prefix="memova-collector-preview-") as temp_dir:
            with Ledger(Path(temp_dir) / "preview.sqlite3") as ledger:
                result = SyncEngine(
                    source=source,
                    ledger=ledger,
                    sink=MockSink(),
                    consent_id="preview-consent-local",
                    device_id="preview-device-local",
                ).run_once()
        result["status"] = "preview_completed"
        result["content_returned"] = False
        result["persisted_after_preview"] = False
        result["remote_upload_performed"] = False
        if args.record_preview:
            _load_consent(_state_dir(args))
            with Ledger(_ledger_path(args)) as ledger:
                ledger.set_metadata("preview_completed_at", utc_now())
                ledger.set_metadata("preview_source", "live" if args.live else "fixture")
            result["preview_gate_recorded"] = True
        _print_json(result)
        return 0
    finally:
        if should_close and isinstance(source, JsonRpcAppServerClient):
            source.close()


def command_status(args: argparse.Namespace) -> int:
    snapshot = inspect_ledger(_ledger_path(args))
    if snapshot is not None:
        metadata = snapshot.pop("metadata")
        payload = snapshot
        payload["mode"] = metadata.get("mode") or "local_m3_not_scheduled"
        payload["preview_completed"] = bool(metadata.get("preview_completed_at"))
        payload["preview_source"] = metadata.get("preview_source")
        payload["project_context_enabled"] = metadata.get("project_context_enabled") == "true"
        payload["project_context_mode"] = metadata.get("project_context_mode") or (
            "full" if payload["project_context_enabled"] else "disabled"
        )
        payload["knowledge_v5_initialized"] = (
            metadata.get("knowledge_v5_initialized") == "true"
        )
        payload["knowledge_v5_server_checkpoint"] = metadata.get(
            "knowledge_v5_server_checkpoint"
        )
        payload["knowledge_v5_last_analyzer_run_id"] = metadata.get(
            "knowledge_v5_last_analyzer_run_id"
        )
        payload["knowledge_v5_retry_required"] = (
            metadata.get("knowledge_v5_retry_required") == "true"
        )
    else:
        payload = {
            "thread_checkpoint_count": 0,
            "acknowledged_item_count": 0,
            "pending_batch_count": 0,
            "acked_batch_count": 0,
            "paused": False,
            "consent_id": None,
            "device_id": None,
            "mode": "unconfigured",
            "preview_completed": False,
            "preview_source": None,
            "project_context_enabled": False,
            "project_context_mode": "disabled",
            "knowledge_v5_initialized": False,
            "knowledge_v5_server_checkpoint": None,
            "knowledge_v5_last_analyzer_run_id": None,
            "knowledge_v5_retry_required": False,
        }
    payload["knowledge_v5_run_pending"] = (
        _state_dir(args) / "knowledge-v5" / "current-run.json"
    ).exists()
    payload["schema_version"] = STATUS_SCHEMA_VERSION
    payload["knowledge_mode"] = "knowledge_v5"
    lock = read_lock(_state_dir(args) / "sync.lock")
    payload["run_active"] = lock is not None
    if args.remote:
        consent = _load_consent(_state_dir(args))
        oauth = _oauth(args)
        payload["oauth"] = oauth.status()
        if not payload["oauth"]["connected"]:
            raise RuntimeError("Collector is not connected to Memova. Run `connect` first.")
        payload["remote"] = RestSink(
            api_base=args.api_base,
            oauth=oauth,
            consent=consent,
        ).status(device_id=str(consent["device_id"]))
    _print_json(payload)
    return 0


def command_diagnose(args: argparse.Namespace) -> int:
    """Inspect the local Collector/V5 control plane without reading conversation content."""

    state_dir = _state_dir(args)
    consent_path = state_dir / "consent.json"
    consent = None
    consent_error = None
    if consent_path.exists():
        try:
            consent = json.loads(consent_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            consent_error = str(exc)
    snapshot = inspect_ledger(_ledger_path(args))
    metadata = (snapshot or {}).get("metadata", {})
    capability = inspect_capabilities(args.codex_path)
    try:
        oauth = _oauth(args).status()
    except RuntimeError as exc:
        oauth = {"connected": False, "error": str(exc)}
    current_run = state_dir / "knowledge-v5" / "current-run.json"
    checks = {
        "consent_active": bool(
            consent
            and consent.get("schema_version") == CONSENT_SCHEMA_VERSION
            and consent.get("status") == "active"
        ),
        "ledger_ready": snapshot is not None,
        "live_preview_completed": bool(
            metadata.get("preview_source") == "live"
            and metadata.get("preview_completed_at")
        ),
        "oauth_connected": bool(oauth.get("connected")),
        "codex_app_server_supported": bool(capability.get("supported")),
        "knowledge_v5_retry_required": metadata.get("knowledge_v5_retry_required")
        == "true",
        "knowledge_v5_run_pending": current_run.exists(),
    }
    recommendations = []
    if consent_error:
        recommendations.append("Repeat setup because consent.json is unreadable.")
    elif not checks["consent_active"]:
        recommendations.append("Run setup and accept the collection policy.")
    if checks["consent_active"] and not checks["live_preview_completed"]:
        recommendations.append("Run and record the live three-task preview before connecting.")
    if checks["live_preview_completed"] and not checks["oauth_connected"]:
        recommendations.append("Connect the Collector to the intended Memova account.")
    if not checks["codex_app_server_supported"]:
        recommendations.append("Update Codex before enabling live collection.")
    if checks["knowledge_v5_run_pending"] or checks["knowledge_v5_retry_required"]:
        recommendations.append("Run sync-once to resume the existing Knowledge V5 run.")
    configured = all(
        checks[name]
        for name in (
            "consent_active",
            "ledger_ready",
            "live_preview_completed",
            "oauth_connected",
            "codex_app_server_supported",
        )
    )
    _print_json(
        {
            "status": "healthy" if configured and not recommendations else "attention_required",
            "knowledge_mode": "knowledge_v5",
            "content_read": False,
            "network_request_performed": False,
            "checks": checks,
            "consent_error": consent_error,
            "oauth": oauth,
            "capability": capability,
            "knowledge_v5_server_checkpoint": metadata.get(
                "knowledge_v5_server_checkpoint"
            ),
            "knowledge_v5_last_analyzer_run_id": metadata.get(
                "knowledge_v5_last_analyzer_run_id"
            ),
            "recommendations": recommendations,
        },
    )
    return 0 if configured and not recommendations else 2


def command_connect(args: argparse.Namespace) -> int:
    consent = _load_consent(_state_dir(args))
    snapshot = inspect_ledger(_ledger_path(args))
    metadata = (snapshot or {}).get("metadata", {})
    if metadata.get("preview_completed_at") is None or metadata.get("preview_source") != "live":
        raise RuntimeError(
            "Record a successful live preview before connecting Memova cloud sync."
        )
    oauth = _oauth(args)
    if args.pairing_grant_stdin:
        pairing_grant = input().strip()
        if not pairing_grant:
            raise RuntimeError("Pairing grant input was empty.")
        result = oauth.connect_with_pairing(
            pairing_grant=pairing_grant,
            device_id=str(consent["device_id"]),
        )
    elif args.pairing_grant_prompt:
        result = oauth.connect_with_pairing(
            pairing_grant=getpass.getpass("Memova pairing grant: ").strip(),
            device_id=str(consent["device_id"]),
        )
    else:
        result = oauth.connect(timeout_seconds=args.timeout_seconds)
    try:
        registration = RestSink(
            api_base=args.api_base,
            oauth=oauth,
            consent=consent,
        ).register_consent()
    except Exception:
        oauth.disconnect()
        raise
    with Ledger(_ledger_path(args)) as ledger:
        ledger.set_metadata("mode", "rest_connected_not_scheduled")
    _print_json(
        {
            **result,
            "server_consent": registration,
            "remote_upload_enabled": True,
            "scheduler_installed": False,
        }
    )
    return 0


def command_prepare_pairing(args: argparse.Namespace) -> int:
    consent = _load_consent(_state_dir(args))
    snapshot = inspect_ledger(_ledger_path(args))
    metadata = (snapshot or {}).get("metadata", {})
    if metadata.get("preview_completed_at") is None or metadata.get("preview_source") != "live":
        raise RuntimeError(
            "Record a successful live preview before preparing Memova pairing."
        )
    result = _oauth(args).prepare_pairing(device_id=str(consent["device_id"]))
    _print_json(result)
    return 0


def command_pause(args: argparse.Namespace) -> int:
    _load_consent(_state_dir(args))
    with Ledger(_ledger_path(args)) as ledger:
        ledger.set_metadata("paused", "true")
    _print_json({"status": "paused"})
    return 0


def command_resume(args: argparse.Namespace) -> int:
    _load_consent(_state_dir(args))
    with Ledger(_ledger_path(args)) as ledger:
        ledger.set_metadata("paused", "false")
    _print_json({"status": "active"})
    return 0


def command_disconnect(args: argparse.Namespace) -> int:
    state_dir = _state_dir(args)
    remote_delete = None
    oauth_result = None
    if args.delete_remote:
        if not args.confirm_delete:
            raise RuntimeError("Remote archive deletion requires --confirm-delete.")
        consent = _load_consent(state_dir)
        oauth = _oauth(args)
        remote_delete = RestSink(
            api_base=args.api_base,
            oauth=oauth,
            consent=consent,
        ).delete(
            {
                "schema_version": "memova_external_conversation_delete_v1",
                "request_id": f"delete-{uuid.uuid4()}",
                "scope": "device",
                "device_id": consent["device_id"],
                "external_thread_id": None,
                "requested_at": utc_now(),
            }
        )
    ledger_snapshot = inspect_ledger(_ledger_path(args))
    mode = (ledger_snapshot or {}).get("metadata", {}).get("mode", "")
    if str(mode).startswith("rest") or args.delete_remote:
        try:
            oauth_result = _oauth(args).disconnect()
        except RuntimeError as exc:
            oauth_result = {"oauth_credential_deleted": False, "error": str(exc)}
    else:
        oauth_result = {"oauth_credential_deleted": False, "reason": "not_connected"}
    consent_path = state_dir / "consent.json"
    if consent_path.exists():
        payload = json.loads(consent_path.read_text(encoding="utf-8"))
        payload["status"] = "revoked"
        consent_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if _ledger_path(args).exists():
        with Ledger(_ledger_path(args)) as ledger:
            ledger.set_metadata("paused", "true")
    _print_json(
        {
            "status": "disconnected",
            "local_archive_deleted": False,
            "remote_delete_requested": args.delete_remote,
            "remote_delete": remote_delete,
            "oauth": oauth_result,
            "message": "Collector stopped; local ledger was retained for audit.",
        },
    )
    return 0


def command_delete_remote(args: argparse.Namespace) -> int:
    if not args.confirm_delete:
        raise RuntimeError("Remote archive deletion requires --confirm-delete.")
    state_dir = _state_dir(args)
    consent = _load_consent(state_dir)
    if args.scope == "thread" and not args.thread_id:
        raise RuntimeError("Thread deletion requires --thread-id.")
    wire_scope = "all_codex_conversations" if args.scope == "all" else args.scope
    oauth = _oauth(args)
    result = RestSink(
        api_base=args.api_base,
        oauth=oauth,
        consent=consent,
    ).delete(
        {
            "schema_version": "memova_external_conversation_delete_v1",
            "request_id": f"delete-{uuid.uuid4()}",
            "scope": wire_scope,
            "device_id": consent["device_id"] if args.scope in {"thread", "device"} else None,
            "external_thread_id": args.thread_id if args.scope == "thread" else None,
            "requested_at": utc_now(),
        }
    )
    credential_result = None
    if args.scope in {"device", "all"}:
        try:
            credential_result = oauth.disconnect()
        except RuntimeError:
            # The deletion transaction already revoked the token; remove only the local copy.
            oauth.store.delete(oauth.account)
            credential_result = {
                "oauth_credential_deleted": True,
                "server_token_revocation_completed": True,
            }
        consent_path = state_dir / "consent.json"
        consent["status"] = "revoked"
        consent_path.write_text(
            json.dumps(consent, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    _print_json(
        {
            "status": "completed",
            "scope": wire_scope,
            "deletion": result,
            "oauth": credential_result,
        }
    )
    return 0


def _add_state_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", default=str(default_state_dir()))


def _add_source(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture")
    group.add_argument("--live", action="store_true")
    parser.add_argument("--codex-path")
    parser.add_argument("--allow-experimental-app-server", action="store_true")


def _add_api_base(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-base", default="https://api.memova.ai")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memova-codex-collector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capabilities = subparsers.add_parser("capabilities")
    capabilities.add_argument("--codex-path")
    capabilities.set_defaults(handler=command_capabilities)

    policy = subparsers.add_parser("policy")
    policy.set_defaults(handler=command_policy)

    setup = subparsers.add_parser("setup")
    _add_state_dir(setup)
    setup.add_argument("--accept-policy", action="store_true")
    setup.add_argument("--consent-id")
    setup.add_argument("--device-id")
    setup.add_argument("--memova-account-hint")
    project_context = setup.add_mutually_exclusive_group()
    project_context.add_argument(
        "--include-project-context",
        action="store_true",
        help=(
            "Include repository display name, branch, and relative path in addition to the "
            "default privacy-minimal repository identity."
        ),
    )
    project_context.add_argument(
        "--disable-project-context",
        action="store_true",
        help="Disable even the default privacy-minimal repository identity.",
    )
    setup.set_defaults(handler=command_setup)

    connect = subparsers.add_parser("connect")
    _add_state_dir(connect)
    _add_api_base(connect)
    connect.add_argument("--timeout-seconds", type=int, default=300)
    pairing_input = connect.add_mutually_exclusive_group()
    pairing_input.add_argument("--pairing-grant-stdin", action="store_true")
    pairing_input.add_argument("--pairing-grant-prompt", action="store_true")
    connect.set_defaults(handler=command_connect)

    prepare_pairing = subparsers.add_parser("prepare-pairing")
    _add_state_dir(prepare_pairing)
    _add_api_base(prepare_pairing)
    prepare_pairing.set_defaults(handler=command_prepare_pairing)

    preview = subparsers.add_parser("preview")
    _add_state_dir(preview)
    _add_source(preview)
    preview.add_argument("--acknowledge-local-read", action="store_true")
    preview.add_argument("--record-preview", action="store_true")
    preview.set_defaults(handler=command_preview)

    sync_once = subparsers.add_parser("sync-once")
    _add_state_dir(sync_once)
    _add_source(sync_once)
    sync_once.add_argument(
        "--sink", choices=["mock", "rest"], default="mock"
    )
    _add_api_base(sync_once)
    sync_once.add_argument("--output")
    sync_once.add_argument(
        "--skip-knowledge-v5",
        action="store_true",
        help=(
            "Archive conversations without running the automatic Knowledge V5 analyzer. "
            "Intended only for rollout diagnostics and rollback."
        ),
    )
    sync_once.add_argument(
        "--thread-id",
        action="append",
        default=[],
        help=(
            "Restrict this run to an exact Codex task id. Repeat for multiple tasks. "
            "Bounded runs refuse unrelated pending outbox batches."
        ),
    )
    sync_once.set_defaults(handler=command_sync_once)

    status_parser = subparsers.add_parser("status")
    _add_state_dir(status_parser)
    _add_api_base(status_parser)
    status_parser.add_argument("--remote", action="store_true")
    status_parser.set_defaults(handler=command_status)

    diagnose = subparsers.add_parser("diagnose")
    _add_state_dir(diagnose)
    _add_api_base(diagnose)
    diagnose.add_argument("--codex-path")
    diagnose.set_defaults(handler=command_diagnose)

    pause = subparsers.add_parser("pause")
    _add_state_dir(pause)
    pause.set_defaults(handler=command_pause)

    resume = subparsers.add_parser("resume")
    _add_state_dir(resume)
    resume.set_defaults(handler=command_resume)

    disconnect = subparsers.add_parser("disconnect")
    _add_state_dir(disconnect)
    _add_api_base(disconnect)
    disconnect.add_argument("--delete-remote", action="store_true")
    disconnect.add_argument("--confirm-delete", action="store_true")
    disconnect.set_defaults(handler=command_disconnect)

    delete_remote = subparsers.add_parser("delete-remote")
    _add_state_dir(delete_remote)
    _add_api_base(delete_remote)
    delete_remote.add_argument("--scope", choices=["thread", "device", "all"], required=True)
    delete_remote.add_argument("--thread-id")
    delete_remote.add_argument("--confirm-delete", action="store_true")
    delete_remote.set_defaults(handler=command_delete_remote)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 2
