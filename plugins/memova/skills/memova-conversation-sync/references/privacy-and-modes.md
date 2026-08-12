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
| Memova archive | Receives selected visible text | Raw archive/ACK/audit | HTTPS | Yes |
| Personal Manual consumer | Independently reads archive snapshots | Own claims/evidence/HTML | Backend-internal | No for archive |
| Knowledge V3 consumer | Independently reads archive snapshots | Own projection state | Backend-internal | No for archive |

Hooks ignore transcript paths, prompts, and assistant text. They persist only event/session/turn ids
and time. Their spool is bounded and disposable.

## Local state and credentials

Default application root:

- macOS: `~/Library/Application Support/Memova/CodexCollector`
- Windows: `%LOCALAPPDATA%\Memova\CodexCollector`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/memova/codex-collector`

SQLite can contain pending visible conversation batches until ACK. Restrictive file permissions are
not encryption; keep the directory out of source control/cloud shares. OAuth tokens must exist only
in macOS Keychain, Windows Credential Manager, or Linux Secret Service. There is no plaintext
fallback.

## Incremental and idempotent delivery

List active/archived metadata every run. Full-read only tasks whose update/archive metadata changed
for the REST target. Compare stable item ids and content hashes to select new, edited, and deleted
messages. Persist batches in an outbox; advance checkpoints only after a matching server ACK. A
target-scoped local-export ACK cannot suppress the first REST upload.

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

The Collector has no projection adapter, projection fields, or consumer status. Personal Manual and
Knowledge V3 each maintain their own snapshots, analysis data, jobs, APIs, and idempotent lifecycle
cursor. They share only the neutral archive as an ancestor and never call or reference each other.
