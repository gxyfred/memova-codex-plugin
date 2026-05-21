#!/usr/bin/env python3
from __future__ import annotations

import argparse

from memova_vault_lib import expand_path, validate_vault, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Memova inbox-first vault/input root.")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    result = validate_vault(expand_path(args.path))
    write_json(result)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
