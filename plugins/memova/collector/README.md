# Memova Codex Conversation Collector M0-M4

This plugin-bundled directory implements the local, version-neutral foundation for Memova Codex
conversation sync. The current local development target is `1.2.0`; it adds the strict V2 archive
batch with privacy-safe project context to the previously completed `1.1.0` Collector line, whose
public-plugin baseline was `1.0.0`.

## Implemented scope

- **M0 capability and privacy gate:** inspect the local App Server protocol without listing or
  reading tasks; require `thread/list`, `thread/read(includeTurns=true)`, visible message item types,
  and the desktop `appServer` source; fail closed when the protocol is incompatible; require an
  extra acknowledgement for the experimental live source.
- **M1 versioned contracts:** consent, canonical batch, durable ACK, status, deletion, content-free
  Hook hint, and synthetic active/archived fixtures.
- **M2 incremental Collector:** list active and archived metadata, full-read only changed tasks,
  preserve every ordered user message and assistant commentary/final answer, filter non-visible and
  tool/file/terminal data, track edits/deletes, use a durable SQLite outbox, and advance
  target-scoped checkpoints only after ACK.
- **M3 stable local operation:** bundle the Collector inside the plugin; install immutable verified
  runtime versions in a user-scoped directory; prevent overlapping runs with an exclusive stale-safe
  lock; provide an explicit-only setup/status/control Skill; write content-free optional Hook hints;
  and render/activate macOS launchd, Windows Task Scheduler, or Linux systemd user schedules after
  consent and a recorded live preview.
- **M4 authenticated cloud archive:** use the signed-in MCP session to mint a short-lived,
  single-use PKCE pairing grant; exchange it for a separate device-bound Collector credential kept
  only in the OS credential store; register device consent; deliver target-scoped incremental
  batches to Memova REST; require a matching durable ACK; and expose thread/device/all deletion.
- **V2 project context:** after MCP pairing, keep the backend-issued, non-authorizing
  owner/workspace repository HMAC key beside OAuth tokens in the OS credential store. A repository
  remote becomes a stable HMAC fingerprint across that owner's paired devices; repositories without
  a usable remote use a device-local opaque identity. The batch may include that fingerprint, a
  display name, branch, and repository-relative working path. Never upload the HMAC key, absolute
  cwd, repository remote URL/credentials/query, or commit SHA. Project/Note/Meeting/Action/etc.
  links remain backend-owned graph relations, not Collector-side projection fields.

Project context is a separate setup choice and defaults to off. Enabling full-history archive does
not implicitly enable this additional metadata class; use `--include-project-context` only after
showing and accepting its disclosure. Disabling it does not affect archive sync.

The mock sink remains available for deterministic development. The `rest` sink is the M4
production-shaped path and performs network traffic only after explicit consent and pairing.
The pairing result and remote status show the server-confirmed Memova account and workspace so the
user can verify the archive destination without revealing OAuth tokens.

## Privacy boundary

Collection is limited to user-visible text from `userMessage` and `agentMessage`. It includes all
intermediate assistant commentary, not only the first prompt and last answer. A visible message can
itself contain credentials or sensitive text; the Collector deliberately does not silently rewrite
it because that would violate the requested complete-history contract. The setup Skill shows this
risk before consent.

Excluded data includes system/developer messages, hidden reasoning, tool calls/results, terminal
output, file-change payloads, file bodies, binary attachments, and subagent traces. App Server is
opened only over local stdio. Live preview returns counts and diagnostics, persists no conversation
content, and requires both `--acknowledge-local-read` and
`--allow-experimental-app-server`.

The bundled Hooks never read prompt/response fields or `transcript_path`. They write only event,
session id, turn id, and timestamp under `$PLUGIN_DATA`. Hooks are optional latency hints; the
periodic scheduler remains the correctness mechanism.

## Consumer-neutral archive boundary

The Collector terminates at a private raw archive and durable ACK. It contains no Personal Manual
or Knowledge V3 projection adapter, status, field, or export sink. Those backend consumers each
freeze their own source snapshot and own their analysis data, jobs, evidence, and lifecycle cursor.
Their only shared ancestor is the raw archive.

## Development commands

From the repository root:

```bash
export PYTHONPATH=plugins/memova/collector

python3 -m memova_collector capabilities
python3 -m memova_collector policy

python3 -m memova_collector setup \
  --state-dir /secure/local/memova-collector \
  --accept-policy

# Optional, separate project-context opt-in:
python3 -m memova_collector setup \
  --state-dir /secure/local/memova-collector \
  --accept-policy \
  --include-project-context

python3 -m memova_collector preview \
  --state-dir /secure/local/memova-collector \
  --fixture plugins/memova/collector/tests/fixtures/app-server-history-v1.json

python3 -m memova_collector prepare-pairing \
  --state-dir /secure/local/memova-collector \
  --api-base https://api.memova.ai

python3 -m memova_collector connect \
  --state-dir /secure/local/memova-collector \
  --api-base https://api.memova.ai \
  --pairing-grant-prompt

python3 -m memova_collector sync-once \
  --state-dir /secure/local/memova-collector \
  --live \
  --allow-experimental-app-server \
  --sink rest \
  --api-base https://api.memova.ai

python3 -m memova_collector status \
  --state-dir /secure/local/memova-collector
```

A live preview must be an explicit local-history read:

```bash
python3 -m memova_collector preview \
  --state-dir /secure/local/memova-collector \
  --live \
  --acknowledge-local-read \
  --allow-experimental-app-server \
  --record-preview
```

Preview content is discarded; recording stores only the completion timestamp/source needed by the
scheduler gate.

## Runtime and scheduler manager

Read-only plan:

```bash
python3 plugins/memova/skills/memova-conversation-sync/scripts/manage_conversation_sync.py plan
```

The mutating commands require `--confirm` and are designed to be called only after the Skill shows
the target and receives user approval:

```bash
python3 plugins/memova/skills/memova-conversation-sync/scripts/manage_conversation_sync.py install --confirm
python3 plugins/memova/skills/memova-conversation-sync/scripts/manage_conversation_sync.py scheduler-plan
python3 plugins/memova/skills/memova-conversation-sync/scripts/manage_conversation_sync.py write-scheduler --confirm
python3 plugins/memova/skills/memova-conversation-sync/scripts/manage_conversation_sync.py activate-scheduler --confirm
```

`write-scheduler` refuses to run without active consent, a recorded live preview, and Collector
OAuth. Installation uses immutable version directories and refuses different bytes under the same
version. Removal
verifies scheduler paths, commands, and file hashes; uninstall moves the whole root to a recoverable
archive instead of deleting local conversation exports.

## Verification

```bash
PYTHONPATH=plugins/memova/collector \
  python3 -m unittest discover -s plugins/memova/collector/tests -v
python3 -m compileall -q plugins/memova/collector plugins/memova/hooks \
  plugins/memova/skills/memova-conversation-sync/scripts
```

No staging or production environment is changed by these local tests.
