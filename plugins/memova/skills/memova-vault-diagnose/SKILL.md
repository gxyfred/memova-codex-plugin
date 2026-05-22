---
name: memova-vault-diagnose
description: Use when the user explicitly asks Memova/Codex to diagnose, validate, repair, or troubleshoot a Memova knowledge-base vault, Memova input root, iCloud folder binding, or meeting-to-vault sync write problem.
---

# Memova Vault Diagnose

Use this skill only when the user explicitly asks to diagnose, validate, repair, or troubleshoot a
Memova vault/input root or a meeting-to-vault sync failure.

## Operating Rules

- Run the low-frequency plugin version check from the plugin root before diagnosis:

  ```bash
  python3 plugins/memova/scripts/version_check.py
  ```

  If it returns `should_remind: true`, show the message and continue diagnosis.
- Prefer deterministic helper scripts first. Use Codex judgment to explain ambiguous raw-input
  folders, likely iOS binding mistakes, and safe repair choices.
- Do not read full private notes or recurse through an entire existing vault unless the user asks.
  Lightweight tree inspection is enough for setup and binding diagnosis.
- Never write repairs before the user approves the exact target path and repair plan.
- Do not overwrite user-authored files. Only missing folders/files and `_memova` machine files may be
  created or overwritten after approval.
- Never store or echo secrets, OAuth tokens, raw credentials, or full private note contents.

## Default Diagnosis Workflow

1. Ask for the Mac path if the user has not provided one. The path can be either a full Memova Vault
   or the scoped Memova input root such as `00_Inbox/Memova`.
2. From the `memova-vault-setup` skill directory, run:

   ```bash
   python3 scripts/diagnose_memova_vault.py --path "<path>" --repair-plan
   ```

   Add `--allow-non-icloud` only when the user knowingly chose a local folder instead of iCloud.
3. Summarize:
   - whether the folder validates,
   - whether it appears to be a full Memova vault or only the Memova input root,
   - missing manifests/state files,
   - raw-input candidates if the selected folder looks like an existing vault.
4. If the report contains a repair plan, explain only the operations with status `create` or
   `overwrite`. Ask for explicit approval before writing.
5. After approval, run:

   ```bash
   python3 scripts/diagnose_memova_vault.py \
     --path "<path>" \
     --repair-plan \
     --apply-repair \
     --confirm-repair
   ```

   Add `--overwrite-machine-files` only when repairing broken `_memova` JSON and the user approved
   overwriting machine files.
6. Validate again and report the final manifest ids and `memova_input_root_relative_path`.

## iOS Binding Checks

When the user is trying to connect the iOS app to the folder:

- Tell iOS to validate `_memova/manifest.json` in the selected Memova input root.
- If the user selected a full new Memova Vault, the iOS app should locate
  `inbox/memova/_memova/manifest.json`.
- If the user selected an existing vault integration, the iOS app should select the exact Memova
  input root folder, for example `00_Inbox/Memova`.
- Compare `input_root_manifest_id`, `vault_template_version`, and
  `memova_input_root_relative_path` with the setup result returned to Memova.
- If `ios_folder_binding_hints` is available from the backend binding, iOS should use its
  `candidate_manifest_paths` against the user-authorized folder before falling back to a shallow
  local search.

## Meeting Sync Troubleshooting

For meeting-to-vault write failures:

- First validate the Memova input root with `diagnose_memova_vault.py`.
- If the folder validates, inspect the sync package file paths and hashes. The iOS app writes package
  `files[].relative_path` below the Memova input root and then reports completion or failure to
  Memova.
- Treat hash mismatches, missing local permissions, iCloud unavailable/offline state, and stale setup
  bindings as separate causes. Ask the user for the failing path or iOS error if Codex cannot infer
  the cause from the report.
