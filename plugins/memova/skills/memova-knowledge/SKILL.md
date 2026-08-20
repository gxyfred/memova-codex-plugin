---
name: memova-knowledge
description: Search and use the current user's Memova Knowledge V5, or prepare a reviewed long-term memory proposal. Use for bounded knowledge questions and explicit proposals; never treat a proposal as an immediate edit to formal knowledge.
---

# Memova Knowledge V5

Use this skill for Memova Knowledge V5 retrieval and reviewed memory proposals. Use only data
returned for the authenticated Memova user.

## Read-only retrieval

For a specific question, call `retrieve_knowledge_context` with the user's query and bounded
defaults. Use `search_knowledge` first only when the user asks to discover, list, or choose matching
projects, concepts, or artifacts. Summarize the returned context and say when evidence is missing or
truncated. Do not attempt a filesystem-wide scan or reconstruct private conversation history.

## Propose an update

`propose_memory_update` creates a review candidate; it does not directly edit the formal profile,
agent memory, wiki, project pages, or graph indexes.

Before calling it:

1. Draft the exact candidate content from evidence already supplied by the user or returned by
   Memova retrieval.
2. Show the target document, project key when applicable, proposal type, title, content,
   sensitivity, evidence references, and related node ids.
3. Explain that Memova will validate/review the candidate before promotion.
4. Obtain explicit approval immediately adjacent to the write.

After approval, call `propose_memory_update` once with `source_agent=codex` and a stable
idempotency key. If the content changes after approval, show the revised candidate and ask again.
Never submit restricted credentials, access tokens, private keys, or raw secrets. Do not claim that
formal Knowledge V5 changed unless a separate Memova status explicitly confirms promotion.

For raw text the user wants stored as a Codex Session, use `memova-explicit-import` instead of a
memory proposal. This skill never enables complete-history collection or a background scheduler.
