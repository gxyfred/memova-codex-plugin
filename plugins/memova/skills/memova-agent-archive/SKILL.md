---
name: memova-agent-archive
description: Archive user-authorized Codex final output files or the exact current task as Markdown into projects/Uncategorized, synchronize them to Memova Blob/PostgreSQL/Knowledge V5, configure ask/automatic preferences, create a manifest-only scheduled task, or move an archived file into a Project.
---

# Memova Agent Archive

Use this workflow when the user asks to save, sync, or automatically archive Codex output in the
Memova Knowledge Base, export the current task as Markdown, configure the archive preference, create
a scheduled archive task, inspect/retry sync state, or move an Agent output into a Project.

## Startup and compatibility

On every invocation, run from the Plugin root:

```bash
python3 plugins/memova/scripts/version_check.py
```

If it reports `should_remind: true`, show the upgrade message and continue. If it fails or returns no
reminder, continue silently. Never run the upgrade command without explicit user confirmation.

Call `get_llm_wiki_sync_capabilities` before the first write. This skill requires Backend/MCP
contract `1.10.0` or newer and template `memova_knowledge_base_v4`. If the Agent archive tools are
absent, do not fall back to broad selected-history import or invent a second tree contract.

If the MCP tools are unavailable and `codex mcp list` reports Memova `Not logged in`, run:

```bash
python3 plugins/memova/scripts/ensure_mcp_login.py
```

For `manual_terminal_login_required`, show the exact command and ask the user to run it in a normal
system Terminal/PowerShell outside the Codex task. For
`login_completed_client_refresh_required`, say OAuth succeeded, do not ask the user to log in again,
and require a full Codex restart plus a new task. Never start a second automatic OAuth attempt.

## Fixed archive scope

Eligible Codex outputs are only final, user-facing Markdown, HTML, plain-text reports, or design
descriptions intentionally produced for the current task. The default destination is always:

```text
projects/Uncategorized/<filename>
```

Do not archive source code, bulk repository files, caches, logs, tests, build outputs, dependency
trees, hidden files/folders, credentials, environment files, suspected secrets, or unrequested
large/binary files. Never enumerate the repository or Codex task history to discover candidates.

Before each upload, use the local helper. It verifies UTF-8, MIME/extension, size, path, and secret
gates; copies the exact authorized file into the bound iCloud Knowledge Base; maintains the stable
ID; and returns the exact MCP tool arguments:

```bash
python3 plugins/memova/scripts/agent_archive.py prepare \
  --source "/absolute/path/to/output.md" \
  --task-id "<current-task-id>" \
  --source-reference "codex://threads/<current-task-id>" \
  --authorize
```

Call only the returned `tool` with the returned `arguments`. After a successful MCP response, ACK
the exact hash with `mark-synced`. Do not mark it synced after a failed or ambiguous call.

## Preference modes

Configure one of these modes with `agent_archive.py configure --vault-root ... --mode ...`:

- `explicit_only`: archive only when the user explicitly asks for a specific file or current task.
- `ask_each_time`: after eligible file output, ask once whether to save it.
- `always_auto_save`: the user's durable opt-in authorizes eligible current-task final outputs; still
  apply every safety filter and never scan beyond files produced in the current task.

This Plugin-owned preference is the enforceable archive policy. Codex local memory may help recall
the preference, but it is generated recall state and must not be edited directly. If the user asks
to enable Codex global memory, guide them to `/memories` or Codex Settings and keep the enforceable
mode in the Plugin helper. Required archive behavior belongs here and in the manifest, not in
`~/.codex/memories`.

## No-file task archive

When the current task produced no eligible file and the mode is `ask_each_time`, run:

```bash
python3 plugins/memova/scripts/agent_archive.py ask-status --task-id "<current-task-id>"
```

If `should_ask` is true, ask at most once whether the user wants to save the current task as a
Markdown document. Immediately record that the question was asked with `mark-asked`, regardless of
the answer. If approved, create one bounded Markdown file containing only the current task's
user-visible user/assistant messages selected for export; do not enumerate other tasks. Run
`prepare` with `--source-kind codex_task_markdown --authorize`, then call the returned
`import_codex_task_markdown` arguments exactly.

## Scheduled task

Create a Codex scheduled task only after the user asks for it. Its prompt must:

1. run `agent_archive.py scan-authorized`;
2. inspect only exact source paths already present in `authorized_outputs`;
3. call the returned MCP request for each changed safe entry;
4. call `mark-synced` only after success;
5. report blocked files without broadening scope.

The schedule must never run `find`, `rg --files`, `git log`, Codex task listing, or history export.
Local scheduled tasks require the computer and Codex app to be available; state that constraint when
creating the schedule.

## Status, retry, and move

- Use `get_llm_wiki_sync_status` for one stable ID or the current Agent archive totals.
- Use `list_llm_wiki_pending_operations` for a bounded pending/failed list.
- Retry only an exact user-selected failed operation with `retry_llm_wiki_operation`.
- For a Project move, move the local iCloud file to the Project folder first, then call
  `move_llm_wiki_agent_file` with the same stable ID and `provider_relation=same_provider`.
- Across providers, require a new stable ID and explicit source-delete confirmation. Call the tool
  with `provider_relation=cross_provider`; it performs copy then confirmed delete. Never emulate a
  cross-provider rename.

Do not claim Blob, iCloud, PostgreSQL, or Knowledge V5 is synchronized until the corresponding MCP
status/receipt says so. Never silently use last-write-wins.
