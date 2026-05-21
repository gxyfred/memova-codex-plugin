---
name: memova-vault-setup
description: Use when the user explicitly invokes Memova to set up, create, inspect, or connect a user-owned Memova knowledge base / LLM Wiki vault from Codex, especially after an iOS setup session has been marked ready for Codex.
---

# Memova Vault Setup

Use this skill only when the user explicitly invokes Memova vault setup, selects a Memova setup
starter prompt, or asks Codex to create/connect a Memova knowledge base. Do not invoke it just
because a prompt mentions Obsidian, iCloud, or notes.

## Operating Rules

- Treat the Memova MCP setup package as the source of truth for setup mode, storage target,
  preferences, and path hints.
- Use the helper scripts in this skill for path discovery, vault inspection, file creation, and
  validation instead of hand-writing large file trees. Resolve `scripts/...` paths relative to this
  skill directory.
- Default to iCloud Drive on Mac for V1. Google Drive and OneDrive are deferred.
- Never write outside the user-approved target directory.
- Do not overwrite existing user files by default. Create missing files and record skipped files.
- For existing vaults, preserve the user's structure and add Memova mapping/metadata instead of
  renaming or moving old files.
- Ask for explicit user approval before creating files, writing into an existing vault, or using a
  non-iCloud target for an iCloud setup.
- Never store secrets, OAuth tokens, raw credentials, or full private note contents in progress
  payloads.

## Default Workflow

When the user asks to set up their Memova knowledge base:

1. Confirm Memova MCP tools are available and authenticated. If not, tell the user to connect the
   Memova MCP server through OAuth and stop.
2. Call `list_pending_knowledge_base_setups`. If there is exactly one ready/running setup, use it.
   If there are multiple, summarize them and ask which one to run.
3. Call `get_knowledge_base_setup_context` for the selected `setup_session_id`.
4. Call `append_knowledge_base_setup_progress` with a concise message that setup has started.
5. Run:

   ```bash
   python3 scripts/find_vault_locations.py
   ```

   Use the output plus the setup package path hints to identify likely iCloud / existing vault
   locations. If the path is still unclear, ask the user for the Mac path.
6. If the user supplied an old vault path, run:

   ```bash
   python3 scripts/inspect_vault.py --path "<old-vault-path>"
   ```

   Keep inspection light; do not recursively read the full vault unless the user asks.
7. Write the MCP `setup_package` object to a temporary JSON file under `/tmp` and run a dry plan:

   ```bash
   python3 scripts/create_memova_vault.py plan \
     --setup-json "/tmp/memova-setup.json" \
     --target-root "<approved-target-path>"
   ```

8. Summarize the plan: target path, setup mode, non-iCloud warning if any, directories to create,
   files to create, files to skip, and project starter pages.
9. Ask for approval. Only after approval, run:

   ```bash
   python3 scripts/create_memova_vault.py create \
     --setup-json "/tmp/memova-setup.json" \
     --target-root "<approved-target-path>" \
     --confirm-create
   ```

10. Validate the result:

    ```bash
    python3 scripts/validate_memova_vault.py \
      --path "<approved-target-path>"
    ```

11. Call `complete_knowledge_base_setup` with a small result summary:
    `manifest_id`, `target_path_summary`, `created_file_count`, `created_dir_count`,
    `skipped_file_count`, and `validation_status`.
12. If setup cannot proceed, call `fail_knowledge_base_setup` with a clear failure code such as
    `setup.path_not_found`, `setup.user_declined`, `setup.validation_failed`, or
    `setup.write_failed`.

## Target Path Guidance

- Common iCloud Drive path on Mac:
  `~/Library/Mobile Documents/com~apple~CloudDocs`
- A good default new-vault target is:
  `~/Library/Mobile Documents/com~apple~CloudDocs/Memova Vault`
- Do not assume iOS and Mac expose the same absolute path. The shared identity is
  `_memova/manifest.json`, not the path string.
- If the user provides a path manually, expand `~`, inspect it, and show the resolved path before
  writing.

## Final Response

End with:

- setup session id,
- target path summary,
- manifest id,
- created/skipped counts,
- validation result,
- what the iOS app should do next: authorize the same folder through Files and verify
  `_memova/manifest.json`.
