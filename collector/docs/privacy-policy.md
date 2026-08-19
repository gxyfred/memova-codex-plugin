# Memova Collector Privacy Notice

Effective date: August 19, 2026

The Memova Collector is operated by MEMOVA LLC. This Collector-specific notice supplements the
[Memova Privacy Policy](https://memova.ai/privacy), last updated May 31, 2026, and explains the
additional local-device processing required for complete Codex-history collection. The general
Privacy Policy controls Memova's handling of personal data except where this notice gives a more
specific Collector disclosure. Privacy questions and requests may be sent to `hello@memova.ai`.

## Separate authorization

Installing the Memova Plugin does not install or authorize the Collector. The Collector is obtained
separately from `https://memova.ai/collector` and does not begin reading Codex history until the user
accepts this notice, reviews a local preview, signs in to Memova, and enables collection. Scheduler
activation is a separate action.

## Data processed

When enabled, the Collector reads active and archived Codex task metadata and the complete
user-visible user/assistant text for changed tasks, including intermediate assistant commentary. It
excludes system/developer instructions, hidden reasoning, tool calls/results, terminal output,
file-change bodies, binary attachments, and subagent traces.

Depending on the user's consent mode, it may also send a privacy-minimal repository fingerprint or
the separately approved repository display name, branch, and repository-relative working path. It
never sends repository remote URLs, embedded credentials, absolute paths, commit SHAs, or the
owner/workspace HMAC key.

Local state includes consent, content-free checkpoints, an SQLite outbox that may temporarily hold
unacknowledged visible text, logs, and one resumable Knowledge V5 changeset. OAuth credentials are
stored only in the operating system credential store. Knowledge V5 analysis temporarily downloads
the authorized Memova Wiki Bundle into a private local workspace and removes it after the attempt.

## Purpose and transport

The data is used to maintain the user's private Memova conversation archive and to perform the
user-authorized Knowledge V5/Personal Manual workflow. Transport uses HTTPS and advances local
checkpoints only after a durable server ACK. Memova does not use Plugin installation as consent and
does not disclose collected content to unrelated integrations through the Collector.

## Retention and controls

Archived content is retained until the user deletes a thread, this device's archive, all Codex
archive data, or the Memova account. Pause, disconnect, scheduler removal, and uninstall stop future
collection but do not delete content already acknowledged by Memova. The Collector provides pause,
resume, device revocation, thread/device/all deletion, status, update, and uninstall controls.

## Device and network requirements

Collection runs only while the user's device and OS user session can execute the scheduled job.
When Memova is unavailable, unsent changes remain in the private local outbox and retry with the
same idempotency identity. The Collector does not require the Codex UI to remain open, but it does
require a supported local Codex App Server and network access for delivery.

## Restricted Data

Complete-history mode can include secrets that the user typed into visible messages. Unlike the
public Plugin's selected-import workflow, the full-history Collector preserves the visible-history
contract and does not claim that pattern filtering can make that archive secret-free. Users and
organizations should apply their own data-loss-prevention and retention policies before enabling
complete-history collection.
