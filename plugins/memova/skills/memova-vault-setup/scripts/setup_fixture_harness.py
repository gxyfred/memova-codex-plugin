#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from memova_vault_lib import (
    apply_plan,
    create_plan,
    inspect_tree,
    raw_input_candidates,
    setup_identity_validation,
    suggested_existing_input_target,
    validate_vault,
)


@dataclass(frozen=True)
class HarnessIssue:
    severity: str
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HarnessCaseResult:
    case_id: str
    status: str
    target_root: str
    issues: list[HarnessIssue]
    details: dict[str, Any] = field(default_factory=dict)


def setup_package(
    *,
    mode: str,
    source_path: Path | None = None,
    session_id: str = "fixture",
    target_path_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_hints: dict[str, Any] = {}
    if source_path is not None:
        source_hints["mac_existing_vault_path"] = str(source_path)
    return {
        "schema_version": "knowledge_base_setup_v1",
        "setup_session_id": session_id,
        "workspace_id": "fixture-workspace",
        "setup_mode": mode,
        "storage_target": "icloud_drive",
        "vault_template_version": "memova_inbox_v1",
        "source_path_hints": source_hints,
        "target_path_hints": target_path_hints or {},
    }


def run_harness(output_root: Path | None = None, *, keep_artifacts: bool = False) -> dict[str, Any]:
    if output_root is None:
        temp_dir = tempfile.mkdtemp(prefix="memova-plugin-setup-fixtures-")
        output_root = Path(temp_dir)
    else:
        output_root.mkdir(parents=True, exist_ok=True)

    results = [
        case_create_new_vault(output_root),
        case_create_new_vault_uses_desired_folder(output_root),
        case_connect_existing_inbox(output_root),
        case_connect_existing_sources(output_root),
        case_existing_vault_root_guard(output_root),
        case_repair_missing_machine_file(output_root),
        case_repair_thin_setup_doc(output_root),
        case_reuse_existing_new_vault_refreshes_identity(output_root),
        case_validate_cli_completion_guard(output_root),
        case_reminder_mark_complete_requires_backend(output_root),
    ]
    issue_count = sum(len([issue for issue in result.issues if issue.severity == "error"]) for result in results)
    report = {
        "schema_version": "memova_plugin_setup_fixture_harness_v1",
        "status": "ok" if issue_count == 0 else "fail",
        "output_root": str(output_root),
        "case_count": len(results),
        "error_count": issue_count,
        "cases": [
            {
                **asdict(result),
                "issues": [asdict(issue) for issue in result.issues],
            }
            for result in results
        ],
    }
    (output_root / "setup-fixture-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if not keep_artifacts and output_root.name.startswith("memova-plugin-setup-fixtures-"):
        shutil.rmtree(output_root, ignore_errors=True)
    return report


def case_create_new_vault(root: Path) -> HarnessCaseResult:
    target = root / "icloud" / "Memova Vault"
    setup = setup_package(mode="create_new_vault", session_id="create-new")
    plan = create_plan(
        target_root=target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=False,
    )
    result = apply_plan(plan, setup)
    validation = validate_vault(target)
    issues = _issues_for_ok_plan(plan, result, validation)
    if validation.get("memova_input_root_relative_path") != "inbox/memova":
        issues.append(
            HarnessIssue(
                "error",
                "wrong_new_vault_input_root",
                "New vault setup should use inbox/memova as the Memova input root.",
            )
        )
    _assert_ios_binding_hints(result, issues, expected_target_kind="memova_vault")
    _assert_new_vault_docs(target, issues)
    _assert_input_root_docs(target / "inbox" / "memova", issues)
    _assert_no_meeting_packets_created(target / "inbox" / "memova", issues)
    return HarnessCaseResult(
        case_id="create_new_vault",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={
            "plan_summary": plan["summary"],
            "validation": validation,
            "ios_folder_binding_hints": result.get("ios_folder_binding_hints"),
        },
    )


def case_create_new_vault_uses_desired_folder(root: Path) -> HarnessCaseResult:
    wrong_target = root / "icloud" / "Memova Vault"
    target = root / "icloud" / "Test111"
    setup = setup_package(
        mode="create_new_vault",
        session_id="create-new-desired-folder",
        target_path_hints={"desired_input_folder_name": "Test111"},
    )
    wrong_plan = create_plan(
        target_root=wrong_target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=False,
    )
    plan = create_plan(
        target_root=target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=False,
    )
    result = apply_plan(plan, setup)
    validation = validate_vault(target)
    issues = _issues_for_ok_plan(plan, result, validation)
    if not wrong_plan.get("errors"):
        issues.append(
            HarnessIssue(
                "error",
                "missing_desired_folder_guard",
                "New vault setup should reject a target root that ignores desired_input_folder_name.",
            )
        )
    if not str(wrong_plan.get("suggested_new_vault_target") or "").endswith("/Test111"):
        issues.append(
            HarnessIssue(
                "error",
                "wrong_desired_folder_suggestion",
                "New vault setup should suggest the desired_input_folder_name path.",
                {"suggested_new_vault_target": wrong_plan.get("suggested_new_vault_target")},
            )
        )
    if not str(result.get("target_root") or "").endswith("/Test111"):
        issues.append(
            HarnessIssue(
                "error",
                "wrong_desired_folder_target_root",
                "New vault setup should create the desired new-vault folder for create_new_vault.",
                {"target_root": result.get("target_root")},
            )
        )
    _assert_ios_binding_hints(result, issues, expected_target_kind="memova_vault")
    _assert_new_vault_docs(target, issues)
    _assert_input_root_docs(target / "inbox" / "memova", issues)
    _assert_no_meeting_packets_created(target / "inbox" / "memova", issues)
    return HarnessCaseResult(
        case_id="create_new_vault_uses_desired_folder",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={
            "wrong_plan_errors": wrong_plan.get("errors"),
            "plan_summary": plan["summary"],
            "validation": validation,
            "ios_folder_binding_hints": result.get("ios_folder_binding_hints"),
        },
    )


def case_connect_existing_inbox(root: Path) -> HarnessCaseResult:
    existing = root / "existing-inbox-vault"
    _seed_existing_vault(existing, ["00_Inbox", "Projects", "Wiki"])
    before_children = _root_children(existing)
    setup = setup_package(
        mode="connect_existing_vault",
        source_path=existing,
        session_id="connect-existing-inbox",
    )
    target = suggested_existing_input_target(setup, existing)
    plan = create_plan(target_root=target, setup=setup, allow_non_icloud=True)
    result = apply_plan(plan, setup)
    validation = validate_vault(target)
    inspection = inspect_tree(existing, max_depth=2, max_entries=100)
    issues = _issues_for_ok_plan(plan, result, validation)
    if not str(target).endswith("00_Inbox/Memova"):
        issues.append(
            HarnessIssue(
                "error",
                "wrong_existing_inbox_target",
                "Existing vault with 00_Inbox should target 00_Inbox/Memova.",
                {"target": str(target)},
            )
        )
    _assert_ios_binding_hints(result, issues, expected_target_kind="memova_input_root")
    _assert_existing_root_preserved(existing, before_children, issues)
    _assert_input_root_docs(target, issues)
    _assert_no_meeting_packets_created(target, issues)
    return HarnessCaseResult(
        case_id="connect_existing_inbox",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={
            "raw_input_candidates": inspection["raw_input_candidates"],
            "validation": validation,
            "ios_folder_binding_hints": result.get("ios_folder_binding_hints"),
        },
    )


def case_connect_existing_sources(root: Path) -> HarnessCaseResult:
    existing = root / "existing-sources-vault"
    _seed_existing_vault(existing, ["Sources", "Notes", "Archive"])
    before_children = _root_children(existing)
    setup = setup_package(
        mode="connect_existing_vault",
        source_path=existing,
        session_id="connect-existing-sources",
    )
    target = suggested_existing_input_target(setup, existing)
    plan = create_plan(target_root=target, setup=setup, allow_non_icloud=True)
    result = apply_plan(plan, setup)
    validation = validate_vault(target)
    candidates = raw_input_candidates(existing)
    issues = _issues_for_ok_plan(plan, result, validation)
    if not str(target).endswith("Sources/Memova"):
        issues.append(
            HarnessIssue(
                "error",
                "wrong_existing_sources_target",
                "Existing vault with Sources should target Sources/Memova.",
                {"target": str(target)},
            )
        )
    if not candidates or candidates[0]["relative_path"] != "Sources":
        issues.append(
            HarnessIssue(
                "error",
                "sources_not_top_candidate",
                "Raw-input candidate scoring should recognize Sources.",
                {"candidates": candidates},
            )
        )
    _assert_ios_binding_hints(result, issues, expected_target_kind="memova_input_root")
    _assert_existing_root_preserved(existing, before_children, issues)
    _assert_input_root_docs(target, issues)
    _assert_no_meeting_packets_created(target, issues)
    return HarnessCaseResult(
        case_id="connect_existing_sources",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={
            "raw_input_candidates": candidates,
            "validation": validation,
            "ios_folder_binding_hints": result.get("ios_folder_binding_hints"),
        },
    )


def case_existing_vault_root_guard(root: Path) -> HarnessCaseResult:
    existing = root / "existing-root-guard-vault"
    _seed_existing_vault(existing, ["Inbox", "Projects"])
    setup = setup_package(
        mode="connect_existing_vault",
        source_path=existing,
        session_id="existing-root-guard",
    )
    plan = create_plan(target_root=existing, setup=setup, allow_non_icloud=True)
    issues: list[HarnessIssue] = []
    if not plan["errors"]:
        issues.append(
            HarnessIssue(
                "error",
                "missing_existing_root_guard",
                "Planning should reject targeting an existing vault root directly.",
            )
        )
    suggested = plan.get("suggested_existing_vault_target") or ""
    if not suggested.endswith("Inbox/Memova"):
        issues.append(
            HarnessIssue(
                "error",
                "missing_existing_root_suggestion",
                "Guard should suggest a Memova child under the detected raw-input folder.",
                {"suggested_existing_vault_target": suggested},
            )
        )
    return HarnessCaseResult(
        case_id="existing_vault_root_guard",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(existing),
        issues=issues,
        details={"errors": plan["errors"], "suggested_existing_vault_target": suggested},
    )


def case_repair_missing_machine_file(root: Path) -> HarnessCaseResult:
    target = root / "repairable-vault"
    setup = setup_package(
        mode="create_new_vault",
        session_id="repair",
        target_path_hints={"desired_input_folder_name": target.name},
    )
    initial_plan = create_plan(
        target_root=target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=True,
    )
    apply_plan(initial_plan, setup)
    missing = target / "inbox" / "memova" / "_memova" / "sync_state.json"
    missing.unlink()
    broken = validate_vault(target)
    repair_plan = create_plan(
        target_root=target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=True,
    )
    result = apply_plan(repair_plan, setup)
    validation = validate_vault(target)
    issues = _issues_for_ok_plan(repair_plan, result, validation)
    if broken["status"] != "fail":
        issues.append(
            HarnessIssue(
                "error",
                "missing_file_not_detected",
                "Validation should fail when a required machine file is missing.",
            )
        )
    if validation["status"] != "ok":
        issues.append(
            HarnessIssue(
                "error",
                "repair_did_not_restore_validation",
                "Re-applying setup should restore a missing machine file.",
                {"validation": validation},
            )
        )
    return HarnessCaseResult(
        case_id="repair_missing_machine_file",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={"broken_validation": broken, "validation": validation},
    )


def case_repair_thin_setup_doc(root: Path) -> HarnessCaseResult:
    target = root / "thin-doc-vault"
    setup = setup_package(
        mode="create_new_vault",
        session_id="thin-doc",
        target_path_hints={"desired_input_folder_name": target.name},
    )
    initial_plan = create_plan(
        target_root=target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=True,
    )
    apply_plan(initial_plan, setup)
    thin_doc = target / "inbox" / "memova" / "README.md"
    thin_doc.write_text("placeholder\n", encoding="utf-8")
    broken = validate_vault(target)
    repair_plan = create_plan(
        target_root=target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=True,
        overwrite_machine_files=True,
    )
    result = apply_plan(repair_plan, setup, overwrite_machine_files=True)
    validation = validate_vault(target)
    issues = _issues_for_ok_plan(repair_plan, result, validation)
    if not broken.get("invalid_required_files"):
        issues.append(
            HarnessIssue(
                "error",
                "thin_doc_not_detected",
                "Validation should fail when a required setup document is too thin.",
                {"broken_validation": broken},
            )
        )
    if "inbox/memova/README.md" not in result.get("overwritten_files", []):
        issues.append(
            HarnessIssue(
                "error",
                "thin_doc_not_overwritten",
                "Repair with overwrite_machine_files should replace Memova-managed setup docs.",
                {"result": result},
            )
        )
    return HarnessCaseResult(
        case_id="repair_thin_setup_doc",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={"broken_validation": broken, "validation": validation},
    )


def case_reuse_existing_new_vault_refreshes_identity(root: Path) -> HarnessCaseResult:
    target = root / "reused-vault"
    first_setup = setup_package(
        mode="create_new_vault",
        session_id="reuse-old-session",
        target_path_hints={"desired_input_folder_name": target.name},
    )
    first_plan = create_plan(
        target_root=target,
        setup=first_setup,
        allow_non_icloud=True,
        allow_existing_nonempty=True,
    )
    apply_plan(first_plan, first_setup)
    user_packet = target / "inbox" / "memova" / "meetings" / "user-created-note.md"
    user_packet.write_text("Existing user packet placeholder\n", encoding="utf-8")

    second_setup = setup_package(
        mode="create_new_vault",
        session_id="reuse-new-session",
        target_path_hints={"desired_input_folder_name": target.name},
    )
    second_plan = create_plan(
        target_root=target,
        setup=second_setup,
        allow_non_icloud=True,
        allow_existing_nonempty=True,
    )
    result = apply_plan(second_plan, second_setup)
    validation = validate_vault(target)
    identity = setup_identity_validation(target, second_setup)
    issues = _issues_for_ok_plan(second_plan, result, validation)
    expected_overwrites = {
        "_memova/manifest.json",
        "inbox/memova/_memova/manifest.json",
    }
    actual_overwrites = set(result.get("overwritten_files") or [])
    missing_overwrites = sorted(expected_overwrites - actual_overwrites)
    if missing_overwrites:
        issues.append(
            HarnessIssue(
                "error",
                "identity_files_not_overwritten",
                "Reusing a Memova directory for a new setup should refresh setup identity manifests.",
                {"missing_overwrites": missing_overwrites, "result": result},
            )
        )
    if identity.get("status") != "ok":
        issues.append(
            HarnessIssue(
                "error",
                "identity_validation_failed",
                "Reused setup should leave local manifests matching the new setup session.",
                {"identity_validation": identity},
            )
        )
    if not user_packet.is_file():
        issues.append(
            HarnessIssue(
                "error",
                "existing_user_file_removed",
                "Refreshing setup identity must not delete existing user or packet files.",
            )
        )
    return HarnessCaseResult(
        case_id="reuse_existing_new_vault_refreshes_identity",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={
            "plan_summary": second_plan["summary"],
            "result": result,
            "validation": validation,
            "identity_validation": identity,
        },
    )


def case_validate_cli_completion_guard(root: Path) -> HarnessCaseResult:
    target = root / "cli-completion-guard-vault"
    setup = setup_package(
        mode="create_new_vault",
        session_id="cli-completion-guard",
        target_path_hints={"desired_input_folder_name": target.name},
    )
    plan = create_plan(
        target_root=target,
        setup=setup,
        allow_non_icloud=True,
        allow_existing_nonempty=True,
    )
    apply_plan(plan, setup)
    setup_json = root / "cli-completion-guard-setup.json"
    setup_json.write_text(json.dumps({"setup_package": setup}, indent=2) + "\n", encoding="utf-8")
    stale_setup = setup_package(
        mode="create_new_vault",
        session_id="cli-completion-stale",
        target_path_hints={"desired_input_folder_name": target.name},
    )
    stale_setup_json = root / "cli-completion-stale-setup.json"
    stale_setup_json.write_text(
        json.dumps({"setup_package": stale_setup}, indent=2) + "\n",
        encoding="utf-8",
    )

    script = Path(__file__).resolve().parent / "validate_memova_vault.py"
    without_setup = _run_json(
        [sys.executable, str(script), "--path", str(target), "--require-setup-identity"],
    )
    with_setup = _run_json(
        [
            sys.executable,
            str(script),
            "--path",
            str(target),
            "--setup-json",
            str(setup_json),
            "--require-setup-identity",
        ],
    )
    with_stale_setup = _run_json(
        [
            sys.executable,
            str(script),
            "--path",
            str(target),
            "--setup-json",
            str(stale_setup_json),
            "--require-setup-identity",
        ],
    )

    issues: list[HarnessIssue] = []
    if without_setup.returncode != 2:
        issues.append(
            HarnessIssue(
                "error",
                "validate_missing_setup_not_blocked",
                "CLI validation should block setup completion when --setup-json is omitted.",
                {"returncode": without_setup.returncode, "stdout": without_setup.stdout},
            )
        )
    if "setup_package_not_provided" not in without_setup.json.get("completion_blockers", []):
        issues.append(
            HarnessIssue(
                "error",
                "validate_missing_setup_blocker_absent",
                "Missing setup package should appear as a completion blocker.",
                {"result": without_setup.json},
            )
        )
    if with_setup.returncode != 0 or not with_setup.json.get("setup_completion_eligible"):
        issues.append(
            HarnessIssue(
                "error",
                "validate_current_setup_not_eligible",
                "CLI validation with the current setup package should be completion eligible.",
                {"returncode": with_setup.returncode, "result": with_setup.json},
            )
        )
    if with_stale_setup.returncode == 0:
        issues.append(
            HarnessIssue(
                "error",
                "validate_stale_setup_not_blocked",
                "CLI validation should fail when local manifests do not match the setup package.",
                {"result": with_stale_setup.json},
            )
        )
    if "setup_identity_validation_failed" not in with_stale_setup.json.get("completion_blockers", []):
        issues.append(
            HarnessIssue(
                "error",
                "validate_stale_setup_blocker_absent",
                "Stale setup identity should appear as a completion blocker.",
                {"result": with_stale_setup.json},
            )
        )

    return HarnessCaseResult(
        case_id="validate_cli_completion_guard",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={
            "without_setup": without_setup.to_details(),
            "with_setup": with_setup.to_details(),
            "with_stale_setup": with_stale_setup.to_details(),
        },
    )


def case_reminder_mark_complete_requires_backend(root: Path) -> HarnessCaseResult:
    reminder_script = (
        Path(__file__).resolve().parents[3] / "scripts" / "kb_setup_reminder.py"
    )
    target = root / "reminder-vault"
    target.mkdir(parents=True, exist_ok=True)

    blocked_home = root / "reminder-home-blocked"
    ok_home = root / "reminder-home-ok"
    blocked = _run_json(
        [sys.executable, str(reminder_script), "--mark-complete", "--vault-path", str(target)],
        env={**os.environ, "HOME": str(blocked_home)},
    )
    allowed = _run_json(
        [
            sys.executable,
            str(reminder_script),
            "--mark-complete",
            "--vault-path",
            str(target),
            "--backend-completed",
            "--setup-session-id",
            "reminder-completed-session",
        ],
        env={**os.environ, "HOME": str(ok_home)},
    )
    allowed_state_path = (
        ok_home
        / ".cache"
        / "memova-codex-plugin"
        / "kb-setup-reminder-v1.json"
    )
    allowed_state = (
        json.loads(allowed_state_path.read_text(encoding="utf-8"))
        if allowed_state_path.exists()
        else {}
    )

    issues: list[HarnessIssue] = []
    if blocked.returncode != 2:
        issues.append(
            HarnessIssue(
                "error",
                "reminder_mark_complete_not_blocked",
                "Reminder mark-complete should require successful backend completion proof.",
                {"returncode": blocked.returncode, "stdout": blocked.stdout},
            )
        )
    if blocked.json.get("error_code") != "backend_setup_completion_required":
        issues.append(
            HarnessIssue(
                "error",
                "reminder_missing_backend_error_code",
                "Blocked reminder mark-complete should expose backend_setup_completion_required.",
                {"result": blocked.json},
            )
        )
    if allowed.returncode != 0 or allowed.json.get("status") != "complete_marked":
        issues.append(
            HarnessIssue(
                "error",
                "reminder_backend_complete_not_allowed",
                "Reminder mark-complete should work after backend completion proof is provided.",
                {"returncode": allowed.returncode, "result": allowed.json},
            )
        )
    if allowed_state.get("setup_session_id") != "reminder-completed-session":
        issues.append(
            HarnessIssue(
                "error",
                "reminder_setup_session_not_recorded",
                "Reminder completion state should record the backend setup session id.",
                {"state": allowed_state},
            )
        )

    return HarnessCaseResult(
        case_id="reminder_mark_complete_requires_backend",
        status="ok" if not _has_error(issues) else "fail",
        target_root=str(target),
        issues=issues,
        details={
            "blocked": blocked.to_details(),
            "allowed": allowed.to_details(),
            "allowed_state": allowed_state,
        },
    )


@dataclass(frozen=True)
class CommandJsonResult:
    returncode: int
    stdout: str
    stderr: str
    json: dict[str, Any]

    def to_details(self) -> dict[str, Any]:
        return {
            "returncode": self.returncode,
            "stdout": self.stdout[:4000],
            "stderr": self.stderr[:4000],
            "json": self.json,
        }


def _run_json(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
) -> CommandJsonResult:
    completed = subprocess.run(  # noqa: S603 - harness commands are fixed local scripts.
        command,
        check=False,
        cwd=str(Path(__file__).resolve().parent),
        env=env,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {}
    return CommandJsonResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        json=payload,
    )


def _seed_existing_vault(path: Path, directories: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".obsidian").mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("# Existing Vault\n", encoding="utf-8")
    for directory in directories:
        (path / directory).mkdir(parents=True, exist_ok=True)
        (path / directory / "user-note.md").write_text("User content\n", encoding="utf-8")


def _root_children(path: Path) -> set[str]:
    return {child.name for child in path.iterdir()} if path.exists() else set()


def _assert_existing_root_preserved(
    existing: Path,
    before_children: set[str],
    issues: list[HarnessIssue],
) -> None:
    created = sorted(_root_children(existing) - before_children)
    if created:
        issues.append(
            HarnessIssue(
                "error",
                "existing_vault_top_level_modified",
                "Connect-existing setup must not create Memova top-level roots.",
                {"created_roots": created},
            )
        )


def _assert_new_vault_docs(root: Path, issues: list[HarnessIssue]) -> None:
    required = {
        "README.md": ["Memova Vault", "inbox/memova", "V1 Scope"],
        "AGENTS.md": ["No memory without source", "No external write without confirmation"],
        "inbox/README.md": ["Inbox", "inbox/memova"],
        "sources/README.md": ["Sources", "Memova V1"],
        "wiki/README.md": ["Wiki", "curated long-term knowledge"],
        "projects/README.md": ["Projects", "project-specific"],
        "daily/README.md": ["Daily", "daily notes"],
        "outputs/README.md": ["Outputs", "finished artifacts"],
        "archive/README.md": ["Archive", "inactive material"],
        "schemas/README.md": ["Schemas", "inbox/memova/schemas"],
    }
    for relative_path, keywords in required.items():
        _assert_doc_contains(root, relative_path, keywords, issues, min_chars=120)


def _assert_input_root_docs(root: Path, issues: list[HarnessIssue]) -> None:
    required = {
        "README.md": [
            "Memova Raw Input Root",
            "Memova Inbox Packet Format v1",
            "meetings/YYYY/MM",
            "sources.md",
            "promotion.json",
        ],
        "AGENTS.md": [
            "Agent Rules",
            "No memory without source",
            "No action without evidence",
            "Reading Order",
        ],
        "INDEX.md": [
            "Memova Inbox Index",
            "meetings/",
            "recent meeting packets",
        ],
        "schemas/meeting_packet.schema.md": [
            "Meeting Packet Schema",
            "sources.md",
            "note.md",
            "promotion.json",
        ],
        "schemas/manifest.schema.md": [
            "Manifest Schema",
            "files",
            "assets_summary",
            "processing",
        ],
        "schemas/packet.schema.md": [
            "Packet JSON Schema",
            "sources",
            "note",
            "processing",
        ],
        "schemas/asset.schema.md": [
            "Asset Manifest Schema",
            "asset_id",
            "role",
            "source_ref",
        ],
        "schemas/promotion.schema.md": [
            "Promotion Schema",
            "promotion_status",
            "not_started",
            "promoted_items",
        ],
    }
    for relative_path, keywords in required.items():
        _assert_doc_contains(root, relative_path, keywords, issues, min_chars=240)


def _assert_doc_contains(
    root: Path,
    relative_path: str,
    keywords: list[str],
    issues: list[HarnessIssue],
    *,
    min_chars: int,
) -> None:
    path = root / relative_path
    if not path.is_file():
        issues.append(
            HarnessIssue(
                "error",
                "missing_setup_doc",
                "Setup should create required human/agent documentation.",
                {"path": str(path), "relative_path": relative_path},
            )
        )
        return
    text = path.read_text(encoding="utf-8")
    if len(text.strip()) < min_chars:
        issues.append(
            HarnessIssue(
                "error",
                "thin_setup_doc",
                "Setup documentation should contain useful non-empty guidance, not placeholders.",
                {"relative_path": relative_path, "char_count": len(text.strip())},
            )
        )
    missing = [keyword for keyword in keywords if keyword not in text]
    if missing:
        issues.append(
            HarnessIssue(
                "error",
                "setup_doc_missing_keywords",
                "Setup documentation is missing expected contract language.",
                {"relative_path": relative_path, "missing_keywords": missing},
            )
        )


def _assert_no_meeting_packets_created(root: Path, issues: list[HarnessIssue]) -> None:
    meetings = root / "meetings"
    packet_dirs = [path for path in meetings.rglob("*") if path.is_dir()] if meetings.exists() else []
    if packet_dirs:
        issues.append(
            HarnessIssue(
                "error",
                "meeting_packets_created_during_setup",
                "Vault setup should create the meetings root but not pre-create concrete meeting packets.",
                {"packet_dirs": [str(path.relative_to(meetings)) for path in packet_dirs[:20]]},
            )
        )


def _assert_ios_binding_hints(
    result: dict[str, Any],
    issues: list[HarnessIssue],
    *,
    expected_target_kind: str,
) -> None:
    hints = result.get("ios_folder_binding_hints")
    if not isinstance(hints, dict):
        issues.append(
            HarnessIssue(
                "error",
                "missing_ios_binding_hints",
                "Setup result should include iOS folder binding hints.",
            )
        )
        return
    if hints.get("schema_version") != "memova_ios_folder_binding_hints_v1":
        issues.append(
            HarnessIssue(
                "error",
                "wrong_ios_binding_hint_schema",
                "iOS folder binding hints should use the expected schema version.",
                {"hints": hints},
            )
        )
    if hints.get("target_kind") != expected_target_kind:
        issues.append(
            HarnessIssue(
                "error",
                "wrong_ios_binding_hint_target_kind",
                "iOS folder binding hints should preserve the setup target kind.",
                {"expected": expected_target_kind, "actual": hints.get("target_kind")},
            )
        )
    if not hints.get("expected_input_root_manifest_id"):
        issues.append(
            HarnessIssue(
                "error",
                "missing_ios_expected_manifest_id",
                "iOS folder binding hints should include the expected input-root manifest id.",
            )
        )
    candidates = hints.get("candidate_manifest_paths")
    if not isinstance(candidates, list) or not candidates:
        issues.append(
            HarnessIssue(
                "error",
                "missing_ios_candidate_manifest_paths",
                "iOS folder binding hints should include candidate manifest paths.",
            )
        )


def _issues_for_ok_plan(
    plan: dict[str, Any],
    result: dict[str, Any],
    validation: dict[str, Any],
) -> list[HarnessIssue]:
    issues: list[HarnessIssue] = []
    if plan["errors"]:
        issues.append(
            HarnessIssue(
                "error",
                "plan_has_errors",
                "Setup plan should not have errors for this fixture.",
                {"errors": plan["errors"]},
            )
        )
    if result.get("status") != "ok":
        issues.append(
            HarnessIssue(
                "error",
                "apply_failed",
                "Setup apply should succeed for this fixture.",
                {"result": result},
            )
        )
    if validation.get("status") != "ok":
        issues.append(
            HarnessIssue(
                "error",
                "validation_failed",
                "Created Memova vault/input root should validate.",
                {"validation": validation},
            )
        )
    return issues


def _has_error(issues: list[HarnessIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Memova vault setup fixture harness.")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_harness(output_root=args.output_root, keep_artifacts=args.keep_artifacts)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"setup fixture harness: {report['status']} ({report['output_root']})")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
