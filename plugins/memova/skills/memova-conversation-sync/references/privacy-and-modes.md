# Conversation Sync Privacy and Modes

## M4 trust boundaries

| Component | Reads conversation content | Writes | Network | Required |
| --- | --- | --- | --- | --- |
| Capability preflight | No | Nothing | No | Yes |
| Hook hint | No | Bounded content-free hint | No | No |
| Live preview | Locally | Preview timestamp only | No | Before first sync |
| Collector | Locally | SQLite outbox/checkpoints | Memova REST | Yes |
| OS credential store | No | OAuth token record | No itself | Yes |
| OS scheduler | No itself | User-scoped definition | No itself | For unattended sync |
| Memova archive | Receives selected visible text; privacy-minimal repository identity by default on fresh setup, or optional full project observations | Raw archive/ACK/audit | HTTPS | Yes |
| Knowledge V5 local analyzer | Complete server-authorized Wiki Bundle | Ephemeral workspace plus one resumable changeset file | Memova REST plus the user's signed-in Codex | After archive ACK |
| Knowledge V5 backend | Archive plus authoritative Memova objects | Bundle, run/lease, validated documents, derived backlinks | Backend-internal | Yes for V5 |

Hooks ignore transcript paths, prompts, and assistant text. They persist only event/session/turn ids
and time. Their spool is bounded and disposable. In 1.4.0 the Collector does not consume this spool;
Hooks are optional audit markers, not sync triggers. The scheduler is the background mechanism.

## Local state and credentials

Default application root:

- macOS: `~/Library/Application Support/Memova/CodexCollector`
- Windows: `%LOCALAPPDATA%\Memova\CodexCollector`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/memova/codex-collector`

SQLite can contain pending visible conversation batches until ACK. During V5 recovery,
`knowledge-v5/current-run.json` can temporarily contain a generated changeset until its durable
server ACK. Analyzer Bundle files exist only under the private analyzer workspace and are removed
after each attempt. Restrictive file permissions are
not encryption; keep the directory out of source control/cloud shares. OAuth tokens must exist only
in macOS Keychain, Windows Credential Manager, or Linux Secret Service. There is no plaintext
fallback.

The V2 batch may include a repository fingerprint. Full mode also includes repository display name,
captured branch, and repository-relative working path. MCP pairing returns a non-authorizing
owner/workspace HMAC
key that is stored only beside OAuth tokens in the OS credential store; it is never written to the
SQLite ledger, status output, logs, or an archive batch. A credential-free canonical remote is
HMACed locally so the same owner can explicitly bind the same repository across paired devices.
Local-only repositories and non-pairing fallback use a device-local opaque identity. The Collector
never sends the absolute working directory, repository remote URL, embedded credentials/query
strings, or commit SHA.

Fresh setup defaults to `privacy_minimal_repository_identity_v1`, which sends only the fingerprint
and identity kind. Full `privacy_safe_repository_context_v1` is a separate explicit choice and adds
display name, branch, and relative path. Disabled sends no context. Existing archive consent does
not silently expand to a new mode during an upgrade. In every mode, explicit repository-to-Project
binding remains backend-owned and auditable; names are never guessed into a binding.

## Incremental and idempotent delivery

List active/archived metadata every run. Full-read only tasks whose update/archive metadata changed
for the REST target. Compare stable item ids and content hashes to select new, edited, and deleted
messages. Persist batches in an outbox; advance checkpoints only after a matching server ACK. A
target-scoped local-export ACK cannot suppress the first REST upload.

The OS scheduler runs the Collector every 5 minutes by default. Each run still lists metadata but
reads and uploads only changed tasks. After archive ACK, the same runtime automatically runs or
resumes Knowledge V5. V5.0 sends the complete authorized Wiki Bundle to an ephemeral, read-only
local `codex exec`; there is no token preflight and no separate Scheduled Task. A no-change run skips
V5 after initialization unless local recovery state exists.

The first production-shaped acceptance run uses exactly three explicitly approved task ids. It
reads and advances checkpoints only for that selection and refuses mixed pending outbox batches.
No scheduler or unbounded REST sync may run before its durable ACK, preventing an initial smoke
test from silently broadening the upload scope.

## Archive, retention, deletion, and independent consumers

The backend stores external conversations separately from Memova app chat tables. Full-history
archive requires explicit opt-in and defaults to retention until thread/device/all deletion or
Memova account deletion. Pause, disconnect, and uninstall do not delete archived data. Idempotency
keys are owner/workspace scoped; replaying the same payload returns the original ACK, while reusing
a key with different bytes is a conflict.

Device/all deletion revokes matching collection consents, deletes normalized raw content, and
scrubs stored batch payloads while retaining non-content audit metadata. Thread deletion removes
only that device-scoped thread. Private Blob raw objects are physically deleted; the database emits
a content-free lifecycle event in the same transaction as its archive state change.

The raw archive has no projection fields. The V5 backend owns authoritative Memova documents,
Bundle authorization, link validation, commits, backlinks, and durable analyzer status. Collector
only orchestrates the local analyzer after ACK; it cannot write target Memova documents directly.
V5 does not dual-write V3.
