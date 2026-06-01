#!/usr/bin/env python3
from __future__ import annotations

import argparse

from memova_vault_lib import (
    expand_path,
    load_setup_json,
    setup_identity_validation,
    validate_vault,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Memova inbox-first vault/input root.")
    parser.add_argument("--path", required=True)
    parser.add_argument(
        "--setup-json",
        help="Optional current backend setup package JSON for setup identity validation.",
    )
    parser.add_argument(
        "--require-setup-identity",
        action="store_true",
        help=(
            "Fail unless --setup-json is present and local manifests match the current setup "
            "package. Use this before complete_knowledge_base_setup."
        ),
    )
    args = parser.parse_args()

    root = expand_path(args.path)
    result = validate_vault(root)
    completion_blockers: list[str] = []

    if args.setup_json:
        try:
            setup = load_setup_json(args.setup_json, required=True)
            identity_validation = setup_identity_validation(root, setup)
        except Exception as exc:  # noqa: BLE001 - surface setup package problems as JSON.
            identity_validation = {
                "schema_version": "memova_setup_identity_validation_v1",
                "status": "fail",
                "error_code": "setup_package_invalid",
                "error": str(exc),
            }
        result["identity_validation"] = identity_validation
        if identity_validation.get("status") != "ok":
            completion_blockers.append("setup_identity_validation_failed")
    else:
        result["identity_validation"] = None
        completion_blockers.append("setup_package_not_provided")

    if result.get("status") != "ok":
        completion_blockers.append("local_validation_failed")

    result["setup_completion_eligible"] = not completion_blockers
    result["completion_blockers"] = completion_blockers
    write_json(result)
    if args.require_setup_identity and "setup_package_not_provided" in completion_blockers:
        return 2
    if args.require_setup_identity:
        return 0 if result["setup_completion_eligible"] else 1
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
