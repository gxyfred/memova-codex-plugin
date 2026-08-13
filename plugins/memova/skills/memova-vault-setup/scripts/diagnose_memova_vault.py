#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from memova_vault_lib import (
    apply_plan,
    create_plan,
    expand_path,
    inspect_tree,
    load_setup_json,
    validate_vault,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose and optionally repair a Memova Knowledge Base V2 or V3 managed root.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--setup-json")
    parser.add_argument("--repair-plan", action="store_true")
    parser.add_argument("--apply-repair", action="store_true")
    parser.add_argument(
        "--confirm-repair",
        action="store_true",
        help="Required with --apply-repair after user approval.",
    )
    parser.add_argument("--allow-non-icloud", action="store_true")
    parser.add_argument("--overwrite-machine-files", action="store_true")
    args = parser.parse_args()

    root = expand_path(args.path)
    setup = load_setup_json(args.setup_json)
    validation = validate_vault(root, setup=setup or None)
    inspection = inspect_tree(root, max_depth=3, max_entries=500)
    diagnosis = diagnose(validation, inspection)
    report: dict[str, Any] = {
        "schema_version": "memova_vault_diagnosis_v1",
        "path": str(root.resolve(strict=False)),
        "status": diagnosis["status"],
        "diagnosis": diagnosis,
        "validation": validation,
        "inspection": {
            "status": inspection["status"],
            "entry_count": inspection.get("entry_count"),
            "truncated": inspection.get("truncated"),
            "has_memova_vault_manifest": inspection.get("has_memova_vault_manifest"),
            "has_memova_input_root_manifest": inspection.get("has_memova_input_root_manifest"),
            "has_obsidian_config": inspection.get("has_obsidian_config"),
            "raw_input_candidates": inspection.get("raw_input_candidates", []),
        },
    }

    if args.repair_plan or args.apply_repair:
        if (
            validation.get("vault_template_version") == "memova_knowledge_base_v3"
            and not setup
            and validation.get("status") != "ok"
        ):
            report["status"] = "fail"
            report["repair_error"] = (
                "V3 repair requires the current backend setup or repair package. "
                "The plugin will not reconstruct V3 files from hardcoded templates."
            )
            write_json(report)
            return 1
        if validation.get("vault_template_version") == "memova_knowledge_base_v3" and not setup:
            report["repair_plan"] = {
                "status": "not_required",
                "vault_template_version": "memova_knowledge_base_v3",
                "operations": [],
            }
            write_json(report)
            return 0
        repair_setup = repair_setup_payload(setup, root, validation, inspection)
        plan = create_plan(
            target_root=root,
            setup=repair_setup,
            allow_non_icloud=args.allow_non_icloud,
            allow_existing_nonempty=True,
            overwrite_machine_files=args.overwrite_machine_files,
        )
        report["repair_plan"] = plan
        if args.apply_repair:
            if not args.confirm_repair:
                report["status"] = "fail"
                report["repair_error"] = "apply repair requires --confirm-repair after user approval"
            else:
                repair_result = apply_plan(
                    plan,
                    repair_setup,
                    overwrite_machine_files=args.overwrite_machine_files,
                )
                post_validation = validate_vault(root, setup=repair_setup)
                report["repair_result"] = repair_result
                report["post_repair_validation"] = post_validation
                report["status"] = "ok" if post_validation["status"] == "ok" else "fail"

    write_json(report)
    return 0 if report["status"] == "ok" else 1


def diagnose(validation: dict[str, Any], inspection: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if inspection["status"] != "ok":
        findings.append(
            {
                "severity": "error",
                "code": "path_not_found",
                "message": "The provided folder does not exist on this Mac.",
            }
        )
    if validation["status"] != "ok":
        if validation.get("missing_roots"):
            findings.append(
                {
                    "severity": "error",
                    "code": "missing_required_roots",
                    "message": "Required Memova vault folders are missing.",
                    "details": {"missing_roots": validation["missing_roots"]},
                }
            )
        if validation.get("missing_machine_files"):
            findings.append(
                {
                    "severity": "error",
                    "code": "missing_machine_files",
                    "message": "Required Memova manifest/state files are missing.",
                    "details": {"missing_machine_files": validation["missing_machine_files"]},
                }
            )
        if validation.get("invalid_required_files"):
            findings.append(
                {
                    "severity": "error",
                    "code": "invalid_required_files",
                    "message": "Required Memova README, AGENTS, or schema files are too thin or missing expected contract language.",
                    "details": {"invalid_required_files": validation["invalid_required_files"]},
                }
            )
        if validation.get("manifest_error"):
            findings.append(
                {
                    "severity": "error",
                    "code": "manifest_json_invalid",
                    "message": "A Memova manifest exists but is not valid JSON.",
                    "details": {"manifest_error": validation["manifest_error"]},
                }
            )
    if validation["status"] == "ok":
        findings.append(
            {
                "severity": "info",
                "code": "valid_memova_target",
                "message": "This folder validates as a Memova vault or managed root.",
            }
        )
    return {
        "status": "ok" if not any(item["severity"] == "error" for item in findings) else "fail",
        "target_kind": validation.get("target_kind"),
        "memova_input_root_path": validation.get("memova_input_root_path"),
        "memova_input_root_relative_path": validation.get("memova_input_root_relative_path"),
        "findings": findings,
    }


def repair_setup_payload(
    setup: dict[str, Any],
    root: Path,
    validation: dict[str, Any],
    inspection: dict[str, Any],
) -> dict[str, Any]:
    if setup:
        repaired = dict(setup)
    else:
        repaired = {
            "schema_version": "knowledge_base_setup_v1",
            "setup_session_id": "local-diagnosis",
            "workspace_id": None,
            "storage_target": "icloud_drive",
            "vault_template_version": "memova_knowledge_base_v2",
            "source_path_hints": {},
            "target_path_hints": {},
        }
    repaired["setup_mode"] = infer_setup_mode(root, validation, inspection)
    return repaired


def infer_setup_mode(root: Path, validation: dict[str, Any], inspection: dict[str, Any]) -> str:
    if validation.get("target_kind") == "memova_vault":
        return "create_new_vault"
    if validation.get("target_kind") == "memova_managed_root":
        return "connect_existing_vault"
    if inspection.get("has_memova_vault_manifest") or (root / "inbox").exists():
        return "create_new_vault"
    return "connect_existing_vault"


if __name__ == "__main__":
    raise SystemExit(main())
