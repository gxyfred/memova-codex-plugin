#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from memova_vault_lib import (
    apply_plan,
    create_plan,
    inspect_tree,
    raw_input_candidates,
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
        "target_path_hints": {},
    }


def run_harness(output_root: Path | None = None, *, keep_artifacts: bool = False) -> dict[str, Any]:
    if output_root is None:
        temp_dir = tempfile.mkdtemp(prefix="memova-plugin-setup-fixtures-")
        output_root = Path(temp_dir)
    else:
        output_root.mkdir(parents=True, exist_ok=True)

    results = [
        case_create_new_vault(output_root),
        case_connect_existing_inbox(output_root),
        case_connect_existing_sources(output_root),
        case_existing_vault_root_guard(output_root),
        case_repair_missing_machine_file(output_root),
        case_repair_thin_setup_doc(output_root),
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
    setup = setup_package(mode="create_new_vault", session_id="repair")
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
    setup = setup_package(mode="create_new_vault", session_id="thin-doc")
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
            "meetings/YYYY/MM",
            "manifest.json",
            "media/audio_manifest.json",
        ],
        "AGENTS.md": [
            "Agent Rules",
            "No memory without source",
            "No action without evidence",
            "Reading Order",
        ],
        "schemas/meeting_packet.schema.md": [
            "Meeting Packet Schema",
            "transcript.md",
            "final_note.json",
            "hashes.json",
        ],
        "schemas/transcript.schema.md": [
            "Transcript Schema",
            "transcript.md",
            "transcript.json",
            "stable post-meeting transcript",
        ],
        "schemas/note.schema.md": [
            "Note Schema",
            "raw_user_note",
            "final_note",
            "Grounding Rules",
        ],
        "schemas/ocr.schema.md": [
            "OCR Schema",
            "ocr/imports.json",
            "pages.json",
            "files/page-001.png",
        ],
        "schemas/attachment.schema.md": [
            "Attachment And Image Schema",
            "attachments.json",
            "images.json",
            "analysis_images",
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
