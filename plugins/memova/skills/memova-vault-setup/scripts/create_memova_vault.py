#!/usr/bin/env python3
from __future__ import annotations

import argparse

from memova_vault_lib import (
    apply_plan,
    create_plan,
    detect_icloud_roots,
    expand_path,
    load_setup_json,
    validate_vault,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or create a Memova inbox-first vault/input root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Print detected iCloud roots.")
    discover_parser.set_defaults(func=run_discover)

    plan_parser = subparsers.add_parser("plan", help="Build a dry-run file operation plan.")
    add_plan_args(plan_parser)
    plan_parser.set_defaults(func=run_plan)

    create_parser = subparsers.add_parser("create", help="Create the vault after approval.")
    add_plan_args(create_parser)
    create_parser.add_argument(
        "--confirm-create",
        action="store_true",
        help="Required to actually write files.",
    )
    create_parser.set_defaults(func=run_create)

    args = parser.parse_args()
    return args.func(args)


def add_plan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--setup-json")
    parser.add_argument("--allow-non-icloud", action="store_true")
    parser.add_argument("--allow-existing-nonempty", action="store_true")
    parser.add_argument(
        "--overwrite-machine-files",
        action="store_true",
        help=(
            "Allow overwriting Memova-managed setup files such as _memova JSON, README, AGENTS, "
            "and schemas. User packet/source files are still skipped."
        ),
    )


def run_discover(_args: argparse.Namespace) -> int:
    write_json(
        {
            "schema_version": "memova_vault_discovery_v1",
            "icloud_roots": detect_icloud_roots(),
        },
    )
    return 0


def run_plan(args: argparse.Namespace) -> int:
    setup = load_setup_json(args.setup_json)
    plan = create_plan(
        target_root=expand_path(args.target_root),
        setup=setup,
        allow_non_icloud=args.allow_non_icloud,
        allow_existing_nonempty=args.allow_existing_nonempty,
        overwrite_machine_files=args.overwrite_machine_files,
    )
    write_json(plan)
    return 0 if not plan["errors"] else 2


def run_create(args: argparse.Namespace) -> int:
    if not args.confirm_create:
        write_json(
            {
                "status": "error",
                "error": "create requires --confirm-create after user approval",
            },
        )
        return 2

    setup = load_setup_json(args.setup_json)
    plan = create_plan(
        target_root=expand_path(args.target_root),
        setup=setup,
        allow_non_icloud=args.allow_non_icloud,
        allow_existing_nonempty=args.allow_existing_nonempty,
        overwrite_machine_files=args.overwrite_machine_files,
    )
    result = apply_plan(plan, setup, overwrite_machine_files=args.overwrite_machine_files)
    if result["status"] != "ok":
        write_json(result)
        return 2

    validation = validate_vault(expand_path(args.target_root))
    result["validation"] = validation
    write_json(result)
    return 0 if validation["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
