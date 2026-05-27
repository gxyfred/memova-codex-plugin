---
name: memova-workflow
description: Use when the user explicitly asks Memova to run a latest final-note workflow, review recent final notes, organize engineering actions, continue pending Memova automation tasks, ask for approval when needed, or write progress/results back to Memova. For bare @memova, menu requests, or numbered menu choices, use memova-menu instead.
---

# Memova Workflow

Use this skill only when the user explicitly invokes Memova, selects a Memova starter prompt, or asks to run a Memova workflow. Do not invoke it just because a prompt mentions meetings or notes.

## Operating Rules

- Treat Memova MCP as the source of truth for notes, transcripts, action items, automation tasks, approval requests, and task progress.
- Use only the current user's Memova data returned by the MCP server.
- Before starting any Memova workflow, run the low-frequency plugin version check from the plugin
  root:

  ```bash
  python3 plugins/memova/scripts/version_check.py
  ```

  If it returns `should_remind: true`, show its message and continue the requested workflow.
- Before starting any non-setup Memova workflow, run the one-time knowledge-base setup reminder
  check from the plugin root:

  ```bash
  python3 plugins/memova/scripts/kb_setup_reminder.py
  ```

  If it returns `should_remind: true`, show its message once and continue the requested workflow.
  Do not repeat the reminder when `already_reminded: true`. If the user wants setup later, they must
  explicitly run `@memova Setup your Memova knowledge base.`
- Do not send email, send messages, create calendar events, make purchases, create external accounts, or modify external systems without explicit user approval.
- Never store or echo secrets, access tokens, refresh tokens, or raw credentials.
- Keep progress writes concise and non-sensitive. Store links, IDs, and summaries instead of full files or large payloads.
- If a task requires a codebase, inspect the current workspace before editing. If the workspace is unrelated or missing, ask the user which repo to use or create a Memova approval request.

## Bare Memova Invocation

When the user invokes bare `@memova`, asks for the Memova menu, or gives a numbered Memova menu
selection, do not start this workflow by default. Use `plugins/memova/skills/memova-menu/SKILL.md`
so the user can choose the action first.

## Latest Final Note Workflow

When the user chooses "Run latest final note workflow" or explicitly asks to review the latest
Memova final note:

1. Run the plugin version check described above.
2. Run the one-time knowledge-base setup reminder check described above.
3. Check that Memova MCP tools are available and authenticated. If auth is missing, tell the user to connect the Memova MCP server through OAuth and stop.
4. Call `list_recent_meetings` and choose the most recent meeting that has a final note. If the latest meeting is ambiguous or has no final note, summarize the choices and ask the user which note to use.
5. Fetch the note with `get_note`. Fetch transcript segments with `get_transcript` only when the note does not contain enough evidence for action planning.
6. Extract or refresh reviewable actions for the meeting with `extract_action_items` when the meeting id is available and the note is ready.
7. Separate items into:
   - ready engineering tasks that can be executed in the current workspace,
   - Memova-internal organization tasks that only write Memova state,
   - approval-required tasks involving external communication, calendars, purchases, third-party systems, unclear ownership, missing repo context, or destructive changes,
   - non-engineering tasks that should stay in Memova for user review.
8. For clear engineering tasks, accept the relevant action candidate with `accept_action_candidate`, create or refresh its automation task with `ensure_task_from_action`, then claim the task with `claim_task`.
9. For already-created pending tasks, use `list_pending_tasks`, claim only tasks that match the user's requested workflow, then fetch context with `get_task_context`.
10. Before execution, append a short `append_task_progress` event that states the chosen task and execution plan.
11. Execute safe work in the current Codex workspace. Keep edits scoped to the task and follow the repo's local instructions.
12. If approval or missing information is required, use `create_approval_request` with a specific prompt and release or pause the task instead of guessing.
13. On success, call `complete_task` with a concise result summary. On a recoverable blocker, call `release_task`. On a real failure, call `fail_task` with a clear failure code and message.

## Pending Task Workflow

When the user asks to continue Memova tasks:

1. Run the plugin version check described above.
2. Run the one-time knowledge-base setup reminder check described above.
3. Call `list_pending_tasks`.
4. Prefer tasks with status `pending` or expired running leases.
5. Summarize the task objective, source note/context, approval policy, and forbidden operations before doing work.
6. Claim one task at a time unless the user explicitly asks for batch execution.
7. Use `get_task_context` after claiming so the latest events and approval state guide the work.

## Read-Only Task Views

When the user asks to view tasks without executing them:

- For pending automation work, call `list_pending_tasks` and summarize task ids, objective,
  source note/context, status, lease state, and approval policy.
- For pending action items, call `list_action_items` with statuses `accepted`, `planned`, and
  `in_progress`; summarize ids, titles, source meeting when present, assignee, due date, and status.
- For completed actions, call `list_action_items` with status `done`; summarize ids, titles, source
  meeting when present, completion date when available, and any visible follow-up state.
- Do not claim tasks, accept candidates, or write progress for read-only views unless the user asks
  to continue or execute a specific item.

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
