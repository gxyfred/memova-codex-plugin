#!/usr/bin/env python3
from __future__ import annotations

import argparse

from memova_vault_lib import expand_path, inspect_tree, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightly inspect an existing vault or folder.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-entries", type=int, default=500)
    args = parser.parse_args()

    result = inspect_tree(
        expand_path(args.path),
        max_depth=max(1, args.max_depth),
        max_entries=max(1, args.max_entries),
    )
    write_json(result)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
