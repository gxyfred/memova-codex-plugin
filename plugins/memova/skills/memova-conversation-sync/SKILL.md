---
name: memova-conversation-sync
description: Set up, authorize, preview, sync, inspect, diagnose, pause, resume, disconnect, delete, update, or uninstall the user-scoped Memova Collector for complete user-visible Codex conversation history and automatic Knowledge V5 analysis. Use only when the user explicitly asks for Memova conversation sync or selects that option from the Memova menu. Supports one-login MCP pairing, isolated Collector credentials, incremental Memova REST upload, durable ACK, ephemeral local Codex analysis, and explicit retention/deletion controls.
---

# Memova Conversation Sync

Manage the opt-in Collector. Resolve paths relative to this Skill's plugin root; do not assume the
repository is current. Read `references/privacy-and-modes.md` before setup, cloud authorization,
scheduler activation, remote deletion, disconnect, or uninstall.

## Route the request

- **Setup/update:** follow the staged workflow.
- **Preview:** explain the local read, then run only after explicit agreement.
- **Connect:** use the signed-in Memova MCP session to create a short-lived PKCE pairing grant.
  Never copy or reuse the Codex MCP bearer token in the Collector.
- **Status:** inspect local counts first. Add `--remote` only when the user asks for server status.
- **Diagnose:** run the local content-free `diagnose` command. It does not read conversations or
  call Memova; use it before proposing setup repair or a V5 resume.
- **Sync now:** the normal REST command is end-to-end: it archives changed Codex history, waits for
  durable ACK, then automatically runs or resumes the server-authorized Knowledge V5 analyzer.
  `--skip-knowledge-v5` is only a disclosed one-run rollout/diagnostic escape hatch.
- **Pause/resume:** keep the scheduler installed; paused runs exit before reading tasks.
- **Disconnect:** revoke Collector OAuth and stop collection without deleting local or remote data.
- **Delete:** require explicit scope and confirmation; send deletion before revoking OAuth.
- **Uninstall:** remove only verified runtime/scheduler files and preserve state recoverably.

## Read-only preflight

Run from the plugin root, using `py -3` on Windows when needed:

```bash
python3 skills/memova-conversation-sync/scripts/manage_conversation_sync.py plan
PYTHONPATH=collector python3 -m memova_collector capabilities
PYTHONPATH=collector python3 -m memova_collector policy
```

Capability inspection must not call `thread/list` or `thread/read`. Report:

- Include all active and archived task messages visible to the user: every user message and all
  assistant commentary/final answers, including intermediate messages.
- Exclude system/developer prompts, hidden reasoning, tool calls/results, terminal output,
  file-change payloads/bodies, binary attachments, and subagent traces.
- Visible messages can contain secrets; do not claim automatic redaction.
- Repository identity lets Knowledge V5 group related tasks and support explicit Project binding.
  Fresh setup defaults to a privacy-minimal fingerprint only. The optional full
  mode also sends repository display name, branch, and repository-relative working path. MCP
  pairing stores a non-authorizing
  owner/workspace HMAC key only in the OS credential record: usable remotes produce a stable HMAC
  fingerprint, while local-only repositories use a device-local opaque identity. Never send that
  key, absolute paths, repository remote URLs/credentials/query strings, or commit SHAs.
- Fresh setup defaults to privacy-minimal repository identity. `--include-project-context` enables
  the disclosed full observations; `--disable-project-context` sends no repository context.
  Existing consent is never silently expanded by an update.
- Hooks are optional content-free activity audit markers. In 1.4.0 they are not consumed as sync
  triggers; scheduler polling is the only background sync mechanism.
- Each run lists metadata, reads only changed tasks, and sends only new/edited/deleted items.
- Server ACK is required before the REST checkpoint advances. Retries reuse the same outbox batch
  and idempotency key; a full history list is never uploaded on every run.
- Raw archive acceptance remains consumer-neutral. Knowledge V5 starts only after that ACK and has
  its own server plan, Bundle revision, lease, changeset, run status, and durable checkpoint.
- V5 invokes the signed-in user's Codex with `--ephemeral`, `--ignore-user-config`,
  `--ignore-rules`, `--sandbox read-only`, and plugin/app/MCP features disabled. It reads the
  complete authorized Wiki Bundle in an isolated private workspace; no unrelated integration,
  separate ChatGPT Scheduled Task, or permanent analyzer process is created.

## Staged setup

### 1. Install/update the runtime

Show `install_root`, `state_dir`, version, and fingerprint from `plan`. After approval:

```bash
python3 skills/memova-conversation-sync/scripts/manage_conversation_sync.py install --confirm
```

Use the returned launcher/state paths. Immutable version directories must not be overwritten.

### 2. Record device collection consent

Show the complete policy. Installation is not collection consent. After explicit acceptance:

- State that full-history archive is off until explicitly enabled.
- State that archived visible conversations are retained until the user deletes a thread, this
  device's archive, all Codex data, or the Memova account.
- State that pause, disconnect, and uninstall stop future collection but do not delete archived
  data.
- Explain that fresh setup sends only a privacy-minimal repository fingerprint by default. Offer
  the full observations as a separate choice and add `--include-project-context` only if accepted.
  Add `--disable-project-context` if the user wants no repository identity. Existing consent keeps
  its stored mode unless the user deliberately changes it.

```bash
python3 "<launcher>" setup --state-dir "<state_dir>" --accept-policy \
  [--include-project-context | --disable-project-context]
```

### 3. Run and record the live preview

Explain that preview reads active and archived histories locally, returns counts/diagnostics,
persists no conversation content, and sends no network request. After approval:

```bash
python3 "<launcher>" preview \
  --state-dir "<state_dir>" \
  --live \
  --acknowledge-local-read \
  --allow-experimental-app-server \
  --record-preview
```

Stop on incompatible App Server. Never parse transcript JSONL/internal databases or scrape UI.

### 4. Pair Memova cloud sync through the existing MCP login

Explain the requested `conversations.read`, `conversations.write`, and `conversations.delete`
Collector scopes and the retention disclosure above. The Codex MCP login also requests
  `knowledge.read` and `knowledge.write` for Memova knowledge workflows. If Memova MCP is not signed in, perform that OAuth login with the
`conversations.connect` scope. Because `codex mcp list` does not expose granted scopes, an existing
login cannot prove it already has these scopes. Explain that reauthorization changes the Memova MCP
session/scopes but does not authorize a scheduler. Obtain separate explicit approval immediately
before running this command from the plugin root:

```bash
python3 plugins/memova/scripts/ensure_mcp_login.py \
  --include-conversation-connect \
  --reauthorize
```

Do not claim the scope is present when the helper reports `already_logged_in_scope_unverified`.
`login_completed_scope_requested` proves only that the scope was requested; the successful pairing
MCP call below is the authorization proof. After explicit pairing approval, run:

```bash
python3 "<launcher>" prepare-pairing \
  --state-dir "<state_dir>" \
  --api-base https://api.memova.ai
```

Call the returned `mcp_tool` using exactly the returned public pairing fields. The tool creates a
five-minute, single-use grant bound to Memova user/workspace, device, Collector client, scopes, and
PKCE challenge. Pass only that pairing grant to the following prompt; do not expose either bearer
token in logs, shell arguments, JSON, SQLite, or environment variables:

```bash
python3 "<launcher>" connect \
  --state-dir "<state_dir>" \
  --api-base https://api.memova.ai \
  --pairing-grant-prompt
```

The Collector exchanges the grant for its own `conversation_sync` access/refresh pair and stores it
only in macOS Keychain, Windows Credential Manager, or Linux Secret Service. Browser Authorization
Code + PKCE remains a fallback only when MCP pairing is unavailable. After pairing, the command
registers device consent but reads/uploads no conversations. Show the server-confirmed Memova
account and workspace from the pairing/consent response and ask the user to verify the destination.

### 5. Run the bounded three-task acceptance

Before any unbounded `sync-once`, scheduler write, or scheduler activation on a fresh setup, require
exactly three user-approved Codex task ids. Show a content-free preview of the exact ids, obtain
final upload approval, and run:

```bash
python3 "<launcher>" sync-once --state-dir "<state_dir>" --live \
  --allow-experimental-app-server --sink rest --api-base https://api.memova.ai \
  --thread-id "<approved_codex_task_id_1>" \
  --thread-id "<approved_codex_task_id_2>" \
  --thread-id "<approved_codex_task_id_3>"
```

The bounded run reads/checkpoints only those three tasks and refuses an existing outbox batch that
contains any other task. Require a durable server ACK before proceeding. Failure must not fall back
to an unbounded run.

### 6. Verify automatic Knowledge V5 completion

The same `sync-once --sink rest` command automatically requests a V5 sync plan after the archive
ACK. The backend provides the complete authorized Wiki Bundle and exact work items. Collector
acquires a workspace lease, verifies Bundle size/hash, runs an ephemeral read-only `codex exec`,
submits the schema-valid changeset, and advances `knowledge_v5_server_checkpoint` only after the
durable changeset ACK. Do not add a token preflight or per-run user confirmation in V5.0.

If submission has an unknown outcome, leave `knowledge-v5/current-run.json` intact. The next
scheduler run must query run status and reuse the stored idempotency key; it must not rerun Codex
when the backend already has a completed ACK. Report per-object accepted/conflict/rejected counts.
The backend alone updates authoritative Memova documents and derives backlinks.

### 7. Offer background sync

Generate the exact plan:

```bash
python3 skills/memova-conversation-sync/scripts/manage_conversation_sync.py scheduler-plan
```

The manager must show all three gates as ready: consent, live preview, OAuth. Ask separately before:

1. `write-scheduler --confirm`
2. `activate-scheduler --confirm`

Do not write or activate it until the bounded three-task run has a durable ACK. Default interval is
5 minutes. The user need not keep Codex open or watch each run, but their OS user session and
supported Codex App Server must remain available.

### 8. Explain optional Hooks accurately

Tell the user that `/hooks` may be used to review/trust `hooks/hooks.json` only if they want local,
content-free activity audit markers. Never infer trust from local files. These markers are not read
by the 1.4.0 Collector and do not make sync faster or more reliable; the scheduler remains the
authoritative background mechanism.

## Control commands

```bash
python3 "<launcher>" status --state-dir "<state_dir>"
python3 "<launcher>" status --state-dir "<state_dir>" --remote
python3 "<launcher>" diagnose --state-dir "<state_dir>"
python3 "<launcher>" pause --state-dir "<state_dir>"
python3 "<launcher>" resume --state-dir "<state_dir>"
python3 "<launcher>" sync-once --state-dir "<state_dir>" --live \
  --allow-experimental-app-server --sink rest --api-base https://api.memova.ai
python3 "<launcher>" disconnect --state-dir "<state_dir>"
```

Do not run `sync-once` merely to test credentials; remote status is read-only. The run lock prevents
overlap. MCP, local-export, and REST checkpoints remain target-scoped.

`diagnose` is local and content-free. It reports consent, preview, OAuth credential presence,
Codex App Server support, pending V5 recovery state, and the next safe action. It must not repair,
sync, or upload anything.

For any "sync now" request, state that the normal REST run includes raw archive followed by V5.
Archive ACK alone does not mean V5 completed; use the `knowledge_v5` result and local V5 checkpoint.

For explicit deletion, show the exact thread/device/all scope and require confirmation:

```bash
python3 "<launcher>" delete-remote --state-dir "<state_dir>" \
  --scope thread --thread-id "<external_thread_id>" --confirm-delete
python3 "<launcher>" delete-remote --state-dir "<state_dir>" \
  --scope device --confirm-delete
python3 "<launcher>" delete-remote --state-dir "<state_dir>" \
  --scope all --confirm-delete
```

Thread deletion keeps sync connected. Device/all deletion revokes the matching Collector credential
after deleting raw content. Downstream consumers receive neutral lifecycle events and independently
invalidate their own evidence and artifacts. The local content-free ledger is retained.

## Uninstall

Run `plan`. Ask before each applicable action:

1. `deactivate-scheduler --confirm`
2. `remove-scheduler --confirm`
3. `uninstall --confirm`

Stop if scheduler files changed. Uninstall moves the runtime/state root to a recoverable archive;
it is not remote deletion.

## Completion language

Say **"Collector is connected"** only after pairing/fallback OAuth and server consent registration.
After a bounded or manual raw REST ACK, say only **"This batch is durably archived."** Say
**"Knowledge V5 is updated"** only after a valid changeset ACK or a `no_work` plan. Say **"Memova
background conversation sync is active"** only after the scheduler successfully activates.
