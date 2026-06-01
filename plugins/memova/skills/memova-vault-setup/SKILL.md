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
- Do not plan or create local setup files if the Memova MCP setup package cannot be retrieved. A
  missing MCP tool, failed OAuth flow, empty pending setup list, or invalid setup package is a hard
  stop, not permission to fall back to local defaults.
- Never report knowledge-base setup as complete unless `complete_knowledge_base_setup` succeeded in
  the same workflow. Local directory validation alone is only "local validation OK"; it is not a
  completed Memova setup and may not be enough for iOS to bind the current setup session.
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
  The exception is Memova setup identity manifests (`_memova/manifest.json` and the input-root
  `_memova/manifest.json`): when a user reuses a Memova directory for a new setup session, these
  files must be refreshed to the current MCP setup package before reporting success.
- For `create_new_vault`, create a new Memova vault with an empty LLM Wiki skeleton and a writable
  Memova input root at `inbox/memova/`.
- For `connect_existing_vault`, preserve the user's existing vault root and create only a scoped
  Memova input root inside the user-confirmed raw-input folder, such as
  `<existing vault>/00_Inbox/Memova`. Do not create Memova `wiki/`, `projects/`, `daily/`, or other
  top-level roots inside an existing vault.
- The setup output must be self-describing. The helper creates non-empty `README.md`, `AGENTS.md`,
  and `schemas/*.schema.md` files that explain the Memova raw-input contract, future meeting packet
  shape, evidence rules, and agent update rules. Do not replace these with empty placeholders.
- These setup docs and schemas are Memova-managed setup files. Existing files are skipped by
  default; overwrite them only with explicit user approval and `--overwrite-machine-files`, for
  example when repairing docs created by an older plugin version.
- Setup should create the `meetings/` root but must not pre-create concrete meeting packet folders;
  iOS writes those later after each meeting.
- Ask for explicit user approval before creating files, writing into an existing vault, or using a
  non-iCloud target for an iCloud setup.
- Never store secrets, OAuth tokens, raw credentials, or full private note contents in progress
  payloads.

## Default Workflow

When the user asks to set up their Memova knowledge base:

1. Run the plugin version check described above.
2. Call `list_pending_knowledge_base_setups` as the setup workflow's first MCP read. If Codex needs
   Memova OAuth and the tool is exposed, let this call trigger that browser login/consent flow.
   If this MCP tool is not exposed in the current thread, run `codex mcp list` before giving
   recovery instructions:
   - If `memova` is listed with Auth `Not logged in`, run the bundled helper from the plugin root:

     ```bash
     python3 plugins/memova/scripts/ensure_mcp_login.py
     ```

     This helper starts `codex mcp login memova --scopes ...` and attempts to open exactly one
     browser authorization URL. The user still has to approve Memova OAuth in the browser. If
     automatic browser opening fails, tell the user to copy the printed `authorization_url` into a
     browser. If the helper reports a `login_error` or `manual_login_command`, tell the user to run
     that command in Windows Terminal/PowerShell or a normal shell. After it reports
     `login_completed`, tell the user to start a new Codex thread if the current thread still does
     not expose the Memova setup tools; Codex does not refresh MCP tool availability mid-thread.
   - If `memova` is not listed, stop and tell the user to upgrade/reinstall the Memova plugin, then
     restart Codex or start a new thread.
   Do not use the filesystem helper scripts without the MCP package. In the final answer for this
   path, do not say "setup complete", "locally set up", or "mark complete"; say that setup is
   blocked because the current Codex thread cannot access the Memova setup MCP tools.
3. If there is exactly one ready/running setup, use it.
   If there are no pending setups, stop and tell the user to create/mark a setup package from the
   Memova app first, or disconnect/reconnect Memova OAuth in Codex with the same Memova account used
   in the iOS app. If there are multiple, summarize them and ask which one to run. After the user
   selects one setup session, call `fail_knowledge_base_setup` for every other ready/running setup
   session returned by the pending list, using:
   - `failure_code`: `setup.superseded_by_selected_session`
   - `failure_message`: `Superseded because the user selected another knowledge-base setup session.`
   - `payload`: include `selected_setup_session_id` and `discarded_setup_session_id`

   Continue only with the selected setup session. This prevents abandoned older setup attempts from
   appearing again on the next setup run.
4. Call `get_knowledge_base_setup_context` for the selected `setup_session_id`.
5. Call `append_knowledge_base_setup_progress` with a concise message that setup has started.
6. Write the MCP `setup_package` object to a temporary JSON file under `/tmp`, then run:

   ```bash
   python3 scripts/find_vault_locations.py \
     --setup-json "/tmp/memova-setup.json"
   ```

   Use the output plus the setup package path hints to identify likely iCloud / existing vault
   locations. If the path is still unclear, ask the user for the Mac path.
7. If the user supplied an old vault path, run:

   ```bash
   python3 scripts/inspect_vault.py --path "<old-vault-path>"
   ```

   Keep inspection light; do not recursively read the full vault unless the user asks.
8. Run a dry plan with the same MCP setup package:

   - For `create_new_vault`, the target root is the new vault root, usually
     the discovery output's `recommended_new_vault`. If the setup package includes
     `target_path_hints.desired_input_folder_name`, that value names the new vault folder, for
     example `<iCloud>/Test111`.
   - For `connect_existing_vault`, the target root is the final Memova input-root folder, usually a
     child of the user's existing raw-input folder such as `<existing vault>/00_Inbox/Memova`.
     Never target the existing vault root itself.

   ```bash
   python3 scripts/create_memova_vault.py plan \
     --setup-json "/tmp/memova-setup.json" \
     --target-root "<approved-target-path>"
   ```

9. Summarize the plan: target path, setup mode, target kind, non-iCloud warning if any,
   directories to create, files to create, files to skip, the self-describing setup docs/schemas to
   create, and the Memova input-root relative path.
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
      --path "<approved-target-path>" \
      --setup-json "/tmp/memova-setup.json" \
      --require-setup-identity
    ```

12. Confirm validation reports `status == "ok"`, `setup_completion_eligible == true`, no
    completion blockers, no missing required documentation/schema/manifest/sync-state files, and
    `identity_validation.status == "ok"`. This proves the local manifest ids and
    `setup_session_id` match the current backend setup package. If identity validation fails, do
    not call `complete_knowledge_base_setup`; repair or fail the setup.
13. Call `complete_knowledge_base_setup` with a small result summary:
    `manifest_id`, `vault_manifest_id`, `input_root_manifest_id`,
    `memova_input_root_relative_path`, `selected_by`, `target_path_summary`,
    `ios_folder_binding_hints`, `created_file_count`, `created_dir_count`,
    `skipped_file_count`, `validation_status`, and `identity_validation`.
14. Mark this Mac as setup-complete for future non-setup workflow reminders:

    ```bash
    python3 plugins/memova/scripts/kb_setup_reminder.py \
      --mark-complete \
      --backend-completed \
      --setup-session-id "<setup_session_id>" \
      --vault-path "<approved-target-path>"
    ```

15. If setup cannot proceed, call `fail_knowledge_base_setup` with a clear failure code such as
    `setup.path_not_found`, `setup.user_declined`, `setup.validation_failed`, or
    `setup.write_failed`.

## Target Path Guidance

- Common iCloud Drive path on Mac:
  `~/Library/Mobile Documents/com~apple~CloudDocs`
- If the setup package has `target_path_hints.desired_input_folder_name`, use that value as the
  create-new-vault folder name. Example: `desired_input_folder_name: Test111` maps to
  `~/Library/Mobile Documents/com~apple~CloudDocs/Test111`.
- If no desired folder name is present, the default new-vault target is:
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
- backend completion result. If `complete_knowledge_base_setup` was not called and did not
  succeed, explicitly say "backend setup is incomplete" and do not say setup is complete,
- what the iOS app should do next: authorize the same vault/input-root folder through Files and
  verify the Memova input-root `_memova/manifest.json`.
