---
name: memova-workflow
description: Use when the user explicitly invokes Memova to run meeting-note workflows from Codex: review recent final notes, organize engineering actions, continue pending Memova automation tasks, ask for approval when needed, and write progress/results back to Memova.
---

# Memova Workflow

Use this skill only when the user explicitly invokes Memova, selects a Memova starter prompt, or asks to run a Memova workflow. Do not invoke it just because a prompt mentions meetings or notes.

## Operating Rules

- Treat Memova MCP as the source of truth for notes, transcripts, action items, automation tasks, approval requests, and task progress.
- Use only the current user's Memova data returned by the MCP server.
- Before starting any non-setup Memova workflow, run the one-time knowledge-base setup reminder
  check from the plugin root:

  ```bash
  python3 plugins/memova/scripts/kb_setup_reminder.py
  ```

  If it returns `should_remind: true`, show its message once and continue the requested workflow.
  Do not repeat the reminder when `already_reminded: true`. If the user wants setup later, they must
  explicitly run `@memova Setup my Memova knowledge base.`
- Do not send email, send messages, create calendar events, make purchases, create external accounts, or modify external systems without explicit user approval.
- Never store or echo secrets, access tokens, refresh tokens, or raw credentials.
- Keep progress writes concise and non-sensitive. Store links, IDs, and summaries instead of full files or large payloads.
- If a task requires a codebase, inspect the current workspace before editing. If the workspace is unrelated or missing, ask the user which repo to use or create a Memova approval request.

## Default Workflow

When the user chooses "Run latest final note workflow" or invokes `@memova` without more detail:

1. Run the one-time knowledge-base setup reminder check described above.
2. Check that Memova MCP tools are available and authenticated. If auth is missing, tell the user to connect the Memova MCP server through OAuth and stop.
3. Call `list_recent_meetings` and choose the most recent meeting that has a final note. If the latest meeting is ambiguous or has no final note, summarize the choices and ask the user which note to use.
4. Fetch the note with `get_note`. Fetch transcript segments with `get_transcript` only when the note does not contain enough evidence for action planning.
5. Extract or refresh reviewable actions for the meeting with `extract_action_items` when the meeting id is available and the note is ready.
6. Separate items into:
   - ready engineering tasks that can be executed in the current workspace,
   - Memova-internal organization tasks that only write Memova state,
   - approval-required tasks involving external communication, calendars, purchases, third-party systems, unclear ownership, missing repo context, or destructive changes,
   - non-engineering tasks that should stay in Memova for user review.
7. For clear engineering tasks, accept the relevant action candidate with `accept_action_candidate`, create or refresh its automation task with `ensure_task_from_action`, then claim the task with `claim_task`.
8. For already-created pending tasks, use `list_pending_tasks`, claim only tasks that match the user's requested workflow, then fetch context with `get_task_context`.
9. Before execution, append a short `append_task_progress` event that states the chosen task and execution plan.
10. Execute safe work in the current Codex workspace. Keep edits scoped to the task and follow the repo's local instructions.
11. If approval or missing information is required, use `create_approval_request` with a specific prompt and release or pause the task instead of guessing.
12. On success, call `complete_task` with a concise result summary. On a recoverable blocker, call `release_task`. On a real failure, call `fail_task` with a clear failure code and message.

## Pending Task Workflow

When the user asks to continue Memova tasks:

1. Run the one-time knowledge-base setup reminder check described above.
2. Call `list_pending_tasks`.
3. Prefer tasks with status `pending` or expired running leases.
4. Summarize the task objective, source note/context, approval policy, and forbidden operations before doing work.
5. Claim one task at a time unless the user explicitly asks for batch execution.
6. Use `get_task_context` after claiming so the latest events and approval state guide the work.

## Approval Guidance

Ask before acting when any of these are true:

- The work would contact another person or external service.
- The task asks for calendar, email, Slack, purchase, billing, production deployment, account creation, deletion, or irreversible mutation.
- The note evidence conflicts with task instructions.
- The relevant repository or environment is unclear.
- Completing the task would require secrets or credentials not already available through approved local configuration.

For Memova-persisted tasks, prefer `create_approval_request` so the decision is visible in Memova. If the user is present in the Codex thread, also ask a concise direct question when that is faster.

## Final Response

End with:

- the Memova note or task ids used,
- what was completed or written back,
- what still needs user approval or follow-up,
- any local verification that was run.
