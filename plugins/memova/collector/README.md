# Memova Codex Conversation Collector M0-M4 + Knowledge V5

This plugin-bundled directory implements the local, version-neutral foundation for Memova Codex
conversation sync. The current local development target is `1.4.0`; it retains the strict,
consumer-neutral archive contract and adds the automatic Knowledge V5 analyzer loop after durable
archive ACK.

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
- **Knowledge V5 analyzer loop:** after a successful archive ACK (and once on first V5 startup),
  request a server sync plan and workspace lease, verify and extract the complete Wiki Bundle into
  an isolated private workspace, invoke `codex exec` with `--ephemeral`, `--sandbox read-only`, and
  plugin/app/MCP features disabled, plus the Bundle changeset schema; then submit the changeset and
  advance the local checkpoint only after a durable server ACK. One private `current-run.json` file
  preserves idempotency across crashes;
  no additional local database table or permanent service is introduced. The existing scheduler
  drives both archive and V5 stages. If the backend's default-off V5 rollout gate is disabled or
  not deployed, the archive ACK remains successful, V5 reports `unavailable`, and the resumable
  state is retained for a later run instead of failing or re-uploading raw history.
- **V2 project context:** after MCP pairing, keep the backend-issued, non-authorizing
  owner/workspace repository HMAC key beside OAuth tokens in the OS credential store. A repository
  remote becomes a stable HMAC fingerprint across that owner's paired devices; repositories without
  a usable remote use a device-local opaque identity. Fresh setup sends only that identity by
  default; full mode may also include a display name, branch, and repository-relative working path.
  Never upload the HMAC key, absolute
  cwd, repository remote URL/credentials/query, or commit SHA. Project/Note/Meeting/Action/etc.
  links remain backend-owned graph relations, not Collector-side projection fields.

Fresh setup defaults to privacy-minimal repository identity. Use `--include-project-context` only
after showing and accepting the disclosure for full observations, or `--disable-project-context`
to send no repository context. Existing consent is not silently expanded. The chosen mode does not
affect archive sync.

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
session id, turn id, and timestamp under `$PLUGIN_DATA`. In 1.4.0 these are optional local audit
markers and are not consumed by the Collector. The periodic scheduler is the background mechanism.

## Consumer-neutral archive and V5 boundary

Raw collection still terminates at a private archive and durable ACK; the archive payload contains
no Personal Manual or knowledge projection fields. Knowledge V5 is a separate post-ACK consumer:
the backend owns plans, Bundles, authorization, validation, commits, backlinks, and the durable run
record, while the local Collector only orchestrates the user's ephemeral Codex analysis. A source
document owns outbound links, and only the backend updates authoritative Memova documents. V5 does
not write V3 data.

The Analyzer uses a stable private workspace root solely so Collection can exclude its own work
defensively. `--ephemeral` prevents Codex rollout persistence, and the workspace is removed after
each attempt. Plugin, remote-plugin catalog, recommended-plugin, app, and app-MCP features are
disabled for the Analyzer subprocess so unrelated integrations are neither initialized nor exposed.
`--skip-knowledge-v5` is a one-run rollout/diagnostic escape hatch; normal REST sync runs V5
automatically and requires no separate Scheduled Task.

## Development commands

From the repository root:

```bash
export PYTHONPATH=plugins/memova/collector

python3 -m memova_collector capabilities
python3 -m memova_collector policy

python3 -m memova_collector setup \
  --state-dir /secure/local/memova-collector \
  --accept-policy

# Optional full project observations (minimal identity is the fresh default):
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

# First production-shaped acceptance run, restricted to exactly three approved tasks:
python3 -m memova_collector sync-once \
  --state-dir /secure/local/memova-collector \
  --live \
  --allow-experimental-app-server \
  --sink rest \
  --api-base https://api.memova.ai \
  --thread-id "<approved_codex_task_id_1>" \
  --thread-id "<approved_codex_task_id_2>" \
  --thread-id "<approved_codex_task_id_3>"

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
