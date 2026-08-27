---
name: memova-knowledge
description: Search and use the current user's Memova Knowledge V5, or create and review a canonical Knowledge Entry proposal. Use for bounded knowledge questions and explicit knowledge writes; never apply a proposal without adjacent user approval.
---

# Memova Knowledge V5

Use this skill for Memova Knowledge V5 retrieval and reviewed Knowledge Entry proposals. Use only data
returned for the authenticated Memova user.

Before any other step on every invocation, run `python3 plugins/memova/scripts/version_check.py`
from the plugin root. If it returns `should_remind: true`, show its upgrade message, but continue
the knowledge workflow. If the check fails or returns no reminder, continue silently. Never run the
upgrade command without explicit user confirmation.

## Read-only retrieval

For a specific question, call `retrieve_knowledge_context` with the user's query and bounded
defaults. Use `search_knowledge` first only when the user asks to discover, list, or choose matching
projects, concepts, or artifacts. Summarize the returned context and say when evidence is missing or
truncated. Do not attempt a filesystem-wide scan or reconstruct private conversation history.

## Create or update a Knowledge Entry

Knowledge Entry is the V5 first-class type for observations, preferences, decisions, ideas,
references, instructions, and other durable information that does not belong to an existing Note,
Project, Action, Overview, Action Web App, Codex Session, or Personal Manual. This workflow creates
or replaces Knowledge Entry only; it does not modify those other business object types in v1.

1. Use bounded retrieval to look for a genuinely matching existing `knowledge_entry`. If one exists
   and the user wants to revise it, use `operation=replace` with its exact object id and revision.
   Do not replace a Note/Project/Action or unrelated entry merely because it is topically similar.
2. If no matching Knowledge Entry exists, use `operation=create`. New facts such as a previously
   unrecorded observation do not need a pre-existing object to modify.
3. Call `create_knowledge_entry_proposal` with the exact title/body, kind, occurrence time and
   precision, sensitivity, source reference/evidence, and a stable idempotency key. Creating the
   proposal does not change searchable Knowledge V5.
4. Show the returned proposal's human-readable content, structured fields, operation, and the
   relevant before-state for replacement. Explain that nothing has been applied yet. Keep proposal
   ids, hashes, and other machine audit fields private by default.
5. Obtain explicit approval immediately adjacent to applying that exact proposal. Then call
   `apply_knowledge_entry_proposal` once with the unchanged proposal id/hash and
   `apply_confirmed=true`.

If the user changes the content after preview, do not apply it. With explicit confirmation, reject
the old proposal using `reject_knowledge_entry_proposal`, then create and review a new proposal.
Use `get_knowledge_entry_proposal` to refresh one exact proposal when needed; never enumerate
proposals. Never submit credentials, access tokens, private keys, or raw secrets. Report formal
Knowledge V5 as changed only after the apply tool returns the canonical entry and revision.

For raw text the user wants stored as a Codex Session, use `memova-explicit-import` instead of a
memory proposal. This skill never enables complete-history collection or a background scheduler.
