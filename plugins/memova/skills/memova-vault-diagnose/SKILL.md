---
name: memova-vault-diagnose
description: Use when the user explicitly asks Memova/Codex to diagnose, validate, repair, or troubleshoot a Memova Knowledge Base V2 or V3 managed root, iCloud folder binding, or meeting-to-vault sync write problem.
---

# Memova Vault Diagnose

Use this skill only when the user explicitly asks to diagnose, validate, repair, or troubleshoot a
Memova Knowledge Base V2/V3 managed root or a meeting-to-vault sync failure.

## Operating Rules

- On every invocation, run the plugin version check from the plugin root before diagnosis:

  ```bash
  python3 plugins/memova/scripts/version_check.py
  ```

  If it returns `should_remind: true`, show the message and continue diagnosis. If the check fails
  or returns no reminder, continue silently. Never run the upgrade command without explicit user
  confirmation.
- Prefer deterministic helper scripts first. Use Codex judgment to explain ambiguous selected
  folders, likely iOS binding mistakes, and safe repair choices.
- Do not read full private notes or recurse through an entire existing vault unless the user asks.
  Lightweight tree inspection is enough for setup and binding diagnosis.
- Never write repairs before the user approves the exact target path and repair plan.
- Do not overwrite user-authored files. Only missing folders/files and `_memova` machine files may be
  created or overwritten after approval.
- Never store or echo secrets, OAuth tokens, raw credentials, or full private note contents.
- Diagnosis/local validation is not setup completion. Do not say a knowledge-base setup is complete
  or mark the setup reminder complete from this skill; only the setup workflow may do that after
  backend `complete_knowledge_base_setup` succeeds.

## Default Diagnosis Workflow

1. Ask for the Mac path if the user has not provided one. The path can be either a new Memova
   knowledge-base root or the root-level `Memova/` managed sub-knowledge-base inside an existing
   user vault.
2. From the `memova-vault-setup` skill directory, run validation first:

   ```bash
   python3 scripts/diagnose_memova_vault.py --path "<path>"
   ```

   Add `--allow-non-icloud` only when the user knowingly chose a local folder instead of iCloud.
   For V3 repair, retrieve the current backend setup or repair package and add
   `--setup-json "/tmp/memova-setup.json" --repair-plan`; do not generate V3 repair files from
   local plugin templates. V2 may use `--repair-plan` without a setup package for compatibility.
3. Summarize:
   - whether the folder validates,
   - whether it appears to be a new Memova vault or an embedded `Memova/` managed root,
   - missing manifests/state files,
   - candidate `Memova/` binding paths if the selected folder looks like an existing vault.
4. If the report contains a repair plan, explain only the operations with status `create` or
   `overwrite`. Ask for explicit approval before writing.
5. After approval, run:

   ```bash
   python3 scripts/diagnose_memova_vault.py \
     --path "<path>" \
     --setup-json "/tmp/memova-setup.json" \
     --repair-plan \
     --apply-repair \
     --confirm-repair
   ```

   Add `--overwrite-machine-files` only when repairing broken `_memova` JSON and the user approved
   overwriting machine files.
6. Validate again and report the template version, final manifest ids, and
   `memova_input_root_relative_path`.

## iOS Binding Checks

When the user is trying to connect the iOS app to the folder:

- Tell iOS to validate `_memova/manifest.json` in the selected Memova managed root.
- If the user selected a full new Memova vault, the selected folder itself should contain
  `_memova/manifest.json`.
- If the user selected an existing vault integration, the iOS app can authorize the existing vault
  root and resolve `Memova/_memova/manifest.json` through `ios_folder_binding_hints`.
- Compare `input_root_manifest_id`, `vault_template_version`, and
  `memova_input_root_relative_path` with the setup result returned to Memova.
- If `ios_folder_binding_hints` is available from the backend binding, iOS should use its
  `candidate_manifest_paths` against the user-authorized folder before falling back to a shallow
  local search.

## Meeting Sync Troubleshooting

For meeting-to-vault write failures:

- First validate the Memova managed root with `diagnose_memova_vault.py`.
- If the folder validates, inspect the sync package file paths and hashes. The iOS app writes package
  `files[].relative_path` below the Memova managed root and then reports completion or failure to
  Memova.
- Treat hash mismatches, missing local permissions, iCloud unavailable/offline state, and stale setup
  bindings as separate causes. Ask the user for the failing path or iOS error if Codex cannot infer
  the cause from the report.
