#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from memova_vault_lib import detect_icloud_roots, load_setup_json, new_vault_folder_name, inspect_tree


def main() -> int:
    parser = argparse.ArgumentParser(description="Find likely Memova/Obsidian vault locations.")
    parser.add_argument("--setup-json", help="Optional Memova setup package JSON for path hints.")
    parser.add_argument("--search-existing", action="store_true")
    parser.add_argument("--max-existing", type=int, default=20)
    args = parser.parse_args()

    setup = load_setup_json(args.setup_json) if args.setup_json else {}
    icloud_roots = detect_icloud_roots(setup)
    existing_vaults = []
    if args.search_existing:
        for candidate in icloud_roots:
            root = Path(candidate["path"])
            if not root.exists():
                continue
            for manifest in root.glob("**/_memova/manifest.json"):
                existing_vaults.append(str(manifest.parent.parent))
                if len(existing_vaults) >= args.max_existing:
                    break
            if len(existing_vaults) >= args.max_existing:
                break

    result = {
        "schema_version": "memova_vault_location_discovery_v1",
        "platform": "macos",
        "icloud_roots": icloud_roots,
        "recommended_new_vault_folder_name": new_vault_folder_name(setup),
        "existing_memova_vaults": existing_vaults,
        "recommended_next_step": (
            "Choose a target path under an existing iCloud root using the setup package's "
            "recommended_new_vault path when setup_mode is create_new_vault."
        ),
    }
    if existing_vaults:
        result["first_existing_vault_inspection"] = inspect_tree(Path(existing_vaults[0]), max_depth=2)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
