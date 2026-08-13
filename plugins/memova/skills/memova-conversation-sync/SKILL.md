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
- **Sync now:** require active consent, a recorded live preview, and Collector OAuth; use REST.
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
- V2 adds a repository fingerprint, display name, branch, and repository-relative working path so
  Knowledge V3 can attach claims to existing objects. MCP pairing stores a non-authorizing
  owner/workspace HMAC key only in the OS credential record: usable remotes produce a stable HMAC
  fingerprint, while local-only repositories use a device-local opaque identity. Never send that
  key, absolute paths, repository remote URLs/credentials/query strings, or commit SHAs.
- Project context is a separate explicit setup opt-in and defaults off. Do not add
  `--include-project-context` merely because archive consent was accepted.
- Hooks are optional content-free latency hints. Scheduler polling remains authoritative.
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
- Separately offer privacy-safe project context. Explain its exact fields and exclusions above.
  Add `--include-project-context` only if the user explicitly accepts this second choice; otherwise
  omit it and leave project context disabled.

```bash
python3 "<launcher>" setup --state-dir "<state_dir>" --accept-policy \
  [--include-project-context]
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
Collector scopes and the retention disclosure above. If Memova MCP is not signed in, perform that
OAuth login once with the `conversations.connect` scope. After explicit approval, run:

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

### 5. Offer background sync

Generate the exact plan:

```bash
python3 skills/memova-conversation-sync/scripts/manage_conversation_sync.py scheduler-plan
```

The manager must show all three gates as ready: consent, live preview, OAuth. Ask separately before:

1. `write-scheduler --confirm`
2. `activate-scheduler --confirm`

Default interval is 15 minutes. The user need not keep Codex open or watch each run, but their OS
user session and supported Codex App Server must remain available.

### 6. Explain optional Hooks

Tell the user to use `/hooks` to review/trust `hooks/hooks.json`. Never infer trust from local files.
Losing Hook hints may add one interval of delay but cannot lose data.

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
overlap. MCP, local export, and REST checkpoints remain target-scoped.

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

Say **"Collector is connected"** only after pairing/fallback OAuth and server consent registration. Say
**"Memova cloud conversation sync is active"** only after the scheduler activates or a REST sync
receives a durable server ACK. Do not report Personal Manual or Knowledge V3 state from Collector
status because those consumers are independent.
