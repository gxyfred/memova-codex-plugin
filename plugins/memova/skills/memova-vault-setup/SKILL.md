---
name: memova-vault-setup
description: Use when the user explicitly invokes Memova to set up, create, inspect, or connect a user-owned Memova raw-input root from Codex, especially after an iOS setup session has been marked ready for Codex.
---

# Memova Vault Setup

Use this skill only when the user explicitly invokes Memova vault setup, selects a Memova setup
starter prompt, or asks Codex to create/connect a Memova knowledge base. Do not invoke it just
because a prompt mentions Obsidian, iCloud, or notes.

## Operating Rules

- Treat the Memova MCP setup package as the source of truth for setup mode, storage target, and
  path hints. Preferences are not collected in inbox-first V1.
- Before starting setup, run the low-frequency plugin version check from the plugin root:

  ```bash
  python3 plugins/memova/scripts/version_check.py
  ```

  If it returns `should_remind: true`, show its message and continue the requested setup workflow.
- Use the helper scripts in this skill for path discovery, vault inspection, file creation, and
  validation instead of hand-writing large file trees. Resolve `scripts/...` paths relative to this
  skill directory.
- Default to iCloud Drive on Mac for V1. Google Drive and OneDrive are deferred.
- Never write outside the user-approved target directory.
- Do not overwrite existing user files by default. Create missing files and record skipped files.
- For `create_new_vault`, create a new Memova vault with an empty LLM Wiki skeleton and a writable
  Memova input root at `inbox/memova/`.
- For `connect_existing_vault`, preserve the user's existing vault root and create only a scoped
  Memova input root inside the user-confirmed raw-input folder, such as
  `<existing vault>/00_Inbox/Memova`. Do not create Memova `wiki/`, `projects/`, `daily/`, or other
  top-level roots inside an existing vault.
- Ask for explicit user approval before creating files, writing into an existing vault, or using a
  non-iCloud target for an iCloud setup.
- Never store secrets, OAuth tokens, raw credentials, or full private note contents in progress
  payloads.

## Default Workflow

When the user asks to set up their Memova knowledge base:

1. Run the plugin version check described above.
2. Confirm Memova MCP tools are available and authenticated. If not, tell the user to connect the
   Memova MCP server through OAuth and stop.
3. Call `list_pending_knowledge_base_setups`. If there is exactly one ready/running setup, use it.
   If there are multiple, summarize them and ask which one to run.
4. Call `get_knowledge_base_setup_context` for the selected `setup_session_id`.
5. Call `append_knowledge_base_setup_progress` with a concise message that setup has started.
6. Run:

   ```bash
   python3 scripts/find_vault_locations.py
   ```

   Use the output plus the setup package path hints to identify likely iCloud / existing vault
   locations. If the path is still unclear, ask the user for the Mac path.
7. If the user supplied an old vault path, run:

   ```bash
   python3 scripts/inspect_vault.py --path "<old-vault-path>"
   ```

   Keep inspection light; do not recursively read the full vault unless the user asks.
8. Write the MCP `setup_package` object to a temporary JSON file under `/tmp` and run a dry plan:

   - For `create_new_vault`, the target root is the new vault root, usually
     `<iCloud>/Memova Vault`.
   - For `connect_existing_vault`, the target root is the final Memova input-root folder, usually a
     child of the user's existing raw-input folder such as `<existing vault>/00_Inbox/Memova`.
     Never target the existing vault root itself.

   ```bash
   python3 scripts/create_memova_vault.py plan \
     --setup-json "/tmp/memova-setup.json" \
     --target-root "<approved-target-path>"
   ```

9. Summarize the plan: target path, setup mode, target kind, non-iCloud warning if any,
   directories to create, files to create, files to skip, and the Memova input-root relative path.
10. Ask for approval. Only after approval, run:

   ```bash
   python3 scripts/create_memova_vault.py create \
     --setup-json "/tmp/memova-setup.json" \
     --target-root "<approved-target-path>" \
     --confirm-create
   ```

11. Validate the result:

    ```bash
    python3 scripts/validate_memova_vault.py \
      --path "<approved-target-path>"
    ```

12. Call `complete_knowledge_base_setup` with a small result summary:
    `manifest_id`, `vault_manifest_id`, `input_root_manifest_id`,
    `memova_input_root_relative_path`, `selected_by`, `target_path_summary`,
    `ios_folder_binding_hints`, `created_file_count`, `created_dir_count`,
    `skipped_file_count`, and `validation_status`.
13. Mark this Mac as setup-complete for future non-setup workflow reminders:

    ```bash
    python3 plugins/memova/scripts/kb_setup_reminder.py \
      --mark-complete \
    --vault-path "<approved-target-path>"
    ```

14. If setup cannot proceed, call `fail_knowledge_base_setup` with a clear failure code such as
    `setup.path_not_found`, `setup.user_declined`, `setup.validation_failed`, or
    `setup.write_failed`.

## Target Path Guidance

- Common iCloud Drive path on Mac:
  `~/Library/Mobile Documents/com~apple~CloudDocs`
- A good default new-vault target is:
  `~/Library/Mobile Documents/com~apple~CloudDocs/Memova Vault`
- Do not assume iOS and Mac expose the same absolute path. The shared identity is the Memova input
  root manifest, not the path string.
- Include `ios_folder_binding_hints` from the helper result when completing setup. iOS uses these
  hints to ask the user for one Files folder authorization, then automatically resolve likely
  manifest paths relative to the authorized folder.
- If the user provides a path manually, expand `~`, inspect it, and show the resolved path before
  writing.

## Final Response

End with:

- setup session id,
- target path summary,
- manifest id,
- input root manifest id,
- Memova input-root relative path,
- iOS authorization hint summary, especially the iCloud relative input-root path when available,
- created/skipped counts,
- validation result,
- what the iOS app should do next: authorize the same vault/input-root folder through Files and
  verify the Memova input-root `_memova/manifest.json`.
