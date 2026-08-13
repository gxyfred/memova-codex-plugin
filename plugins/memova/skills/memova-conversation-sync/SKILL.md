---
name: memova-conversation-sync
description: Set up, authorize, preview, sync, inspect, pause, resume, disconnect, delete, update, or uninstall the user-scoped Memova Collector for complete user-visible Codex conversation history. Use only when the user explicitly asks for Memova conversation sync or selects that option from the Memova menu. M4 supports one-login MCP pairing, isolated Collector credentials, incremental Memova REST upload, server ACK, and explicit long-term retention/deletion controls.
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
- **Sync now:** clarify whether the user means Codex-to-archive, archive-to-V3, or end-to-end. The
  first uses Collector REST; the second uses the V3 MCP trigger on already-durable archive data;
  end-to-end waits for the Collector ACK before invoking the V3 trigger.
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
- V2 can add repository identity so Knowledge V3 can group related tasks and support an explicit
  Project binding. Fresh setup defaults to a privacy-minimal fingerprint only. The optional full
  mode also sends repository display name, branch, and repository-relative working path. MCP
  pairing stores a non-authorizing
  owner/workspace HMAC key only in the OS credential record: usable remotes produce a stable HMAC
  fingerprint, while local-only repositories use a device-local opaque identity. Never send that
  key, absolute paths, repository remote URLs/credentials/query strings, or commit SHAs.
- Fresh setup defaults to privacy-minimal repository identity. `--include-project-context` enables
  the disclosed full observations; `--disable-project-context` sends no repository context.
  Existing consent is never silently expanded by an update.
- Hooks are optional content-free activity audit markers. In 1.3.0 they are not consumed as sync
  triggers; scheduler polling is the only background sync mechanism.
- Each run lists metadata, reads only changed tasks, and sends only new/edited/deleted items.
- Server ACK is required before the REST checkpoint advances. Retries reuse the same outbox batch
  and idempotency key; a full history list is never uploaded on every run.
- Raw archive acceptance is consumer-neutral. Personal Manual and Knowledge V3 independently read
  the archive; neither consumer is part of Collector ACK or status.

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
`knowledge.read` and `knowledge.write` so it can show and control the separate Knowledge V3
consumer. If Memova MCP is not signed in, perform that OAuth login with the
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

### 6. Offer Knowledge V3 processing separately

Archive sync and Knowledge V3 processing are independent permissions. After the bounded archive
batch has a durable server ACK, use `get_conversation_knowledge_status` to show the backend state.
Do not infer V3 state from Collector status.

If the user wants the archive continuously processed into Knowledge V3, explain and obtain one
explicit confirmation for ongoing automatic incrementals. Then call
`enable_conversation_knowledge` with `continuous_processing_confirmed=true`. This creates a
no-model preflight for the one-time historical backfill; it does not start paid model work.

Show the returned run id and exact maximum input tokens, output tokens, model calls, estimated USD
cost, model deployment, and snapshot size. Only after the user explicitly approves those finite
initial values, call `confirm_conversation_knowledge_initial_run` with the same run id, currency
`USD`, `initial_backfill_confirmed=true`, and bounds at least as large as the displayed maxima.
Those user-confirmed bounds apply only to that historical run. Later changed archive data is
processed automatically under backend-owned per-run budgets and safety limits; do not ask for a
new approval for each ordinary incremental.

The backend checks durable archive events at least once per minute, waits for 60 seconds of quiet to
coalesce normal bursts, and never waits more than 10 minutes. If the user explicitly asks to process
already-uploaded changes immediately, call `trigger_conversation_knowledge_sync_now` with a fresh
stable idempotency key; this bypasses the quiet window but not safety checks.

If status is `paused_system_safety`, perform only read-only diagnosis: show the triggering preflight,
current frozen run budget, server safety limits, and preserved archive/V3 checkpoint state. Do not
repeat initial confirmation, change limits, retry, deploy, or requeue automatically. Escalate for an
operational fix or bounded partition plan; any backend limit change or requeue requires its own
explicit approval.

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
by the 1.3.0 Collector and do not make sync faster or more reliable; the scheduler remains the
authoritative background mechanism.

## Control commands

```bash
python3 "<launcher>" status --state-dir "<state_dir>"
python3 "<launcher>" status --state-dir "<state_dir>" --remote
python3 "<launcher>" pause --state-dir "<state_dir>"
python3 "<launcher>" resume --state-dir "<state_dir>"
python3 "<launcher>" sync-once --state-dir "<state_dir>" --live \
  --allow-experimental-app-server --sink rest --api-base https://api.memova.ai
python3 "<launcher>" disconnect --state-dir "<state_dir>"
```

Do not run `sync-once` merely to test credentials; remote status is read-only. The run lock prevents
overlap. MCP, local-export, and REST checkpoints remain target-scoped.

For any "sync now" request, state which stage will run. An end-to-end request must execute
Collector REST first, verify its durable ACK, then call the V3 sync-now tool and report V3 status
only from MCP. Neither ACK nor a queued V3 run means projection has completed.

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
After a bounded or manual REST ACK, say only **"This batch is durably archived."** Say **"Memova
background conversation sync is active"** only after the scheduler successfully activates. Report
Knowledge V3 state only from the dedicated MCP status tool because backend consumers are
independent from Collector status.
