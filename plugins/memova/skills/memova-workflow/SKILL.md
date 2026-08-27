---
name: memova-workflow
description: Review or run existing Memova automation tasks when the user asks to list unfinished tasks, assess whether they are internally executable or waiting for confirmation, run a selected task, or write progress/results back to Memova. Preserve waiting_for_user as guarded. For bare @memova, menu requests, or numbered menu choices, use memova-menu instead.
---

# Memova Workflow

Use this skill only when the user explicitly invokes Memova, selects a Memova starter prompt, or asks to run a Memova workflow. Do not invoke it just because a prompt mentions meetings or notes.

## Operating Rules

- Treat Memova MCP as the source of truth for notes, transcripts, automation tasks, approval requests, and task progress.
- User-facing Codex work starts from `automation_tasks`. Do not recreate tasks from action
  candidates when the user asks to run Memova Codex work.
- Use only the current user's Memova data returned by the MCP server.
- Before starting any Memova workflow on every invocation, run the plugin version check from the
  plugin root:

  ```bash
  python3 plugins/memova/scripts/version_check.py
  ```

  If it returns `should_remind: true`, show its message and continue the requested workflow. If the
  check fails or returns no reminder, continue silently. Never run the upgrade command without
  explicit user confirmation.
- Before starting any non-setup Memova workflow, run the one-time knowledge-base setup reminder
  check from the plugin root:

  ```bash
  python3 plugins/memova/scripts/kb_setup_reminder.py
  ```

  If it returns `should_remind: true`, show its message once and continue the requested workflow.
  Do not repeat the reminder when `already_reminded: true`. If the user wants setup later, they must
  explicitly run `@memova Set up knowledge base.`
- Do not send email, send messages, create calendar events, make purchases, create external accounts, or modify external systems without explicit user approval.
- Never store or echo secrets, access tokens, refresh tokens, or raw credentials.
- Keep progress writes concise and non-sensitive. Store links, IDs, and summaries instead of full files or large payloads.
- Keep schema names, machine provenance/version tags, fixture markers, and synthetic-data labels
  internal by default. Translate them into plain language such as "the reviewer demo records" or
  "synthetic Memova data" instead of echoing raw tags in progress or final responses.
- If a task requires a codebase, inspect the current workspace before editing. If the workspace is unrelated or missing, ask the user which repo to use or create a Memova approval request.

## Bare Memova Invocation

When the user invokes bare `@memova`, asks for the Memova menu, or gives a numbered Memova menu
selection, do not start this workflow by default. Use `plugins/memova/skills/memova-menu/SKILL.md`
so the user can choose the action first.

## Latest Note Automation Task Workflow

When the user chooses "Run latest note automation tasks" or explicitly asks to run Codex tasks for
the latest Memova note:

1. Run the plugin version check described above.
2. Run the one-time knowledge-base setup reminder check described above.
3. Call `list_latest_note_automation_tasks` with `statuses=["pending","running"]`,
   `claimable_only=true`, and a reasonable `limit` such as `20`.
   If this MCP tool is unavailable, run `codex mcp list`. If `memova` is listed with Auth
   `Not logged in`, run `python3 plugins/memova/scripts/ensure_mcp_login.py` from the plugin root.
   The helper starts MCP OAuth login and attempts to open one browser authorization URL; the user
   still approves in the browser. If automatic browser opening fails, tell the user to copy the
   printed `authorization_url` into a browser. If the helper reports a `login_error` or
   `manual_login_command`, tell the user to run that command in Windows Terminal/PowerShell or a
   normal shell. After successful login, tell the user to start a new Codex thread if this thread
   still does not expose the Memova MCP tools. If `memova` is not listed, tell the user to
   upgrade/reinstall the Memova plugin and restart Codex.
4. If no latest ready note exists, say so and stop. Do not call `extract_action_items`.
5. If a latest note exists but has no claimable automation tasks, summarize the latest note/meeting
   identifiers and say there are no unfinished Codex automation tasks for it. Do not create new
   tasks.
6. If tasks are returned, summarize user-visible titles/objectives, source note/meeting titles,
   status, owner, approval needs, and safety constraints. Keep task, note, meeting, action, lease,
   and event ids internal by default. Show an internal id only when the user asks for technical
   details or when human-readable details cannot disambiguate the target. If there are multiple
   tasks, choose the first clearly safe task or ask the user which one to run when the right order
   is ambiguous.
7. Claim one task at a time with `claim_task`, then call `get_task_context`.
8. Before execution, append a short `append_task_progress` event that states the chosen task and execution plan.
9. Execute safe work in the current Codex workspace. Keep edits scoped to the task and follow the repo's local instructions.
10. If approval or missing information is required, use `create_approval_request` with a specific prompt and stop instead of guessing. If the user is present in the Codex thread, also ask directly when that is faster.
11. On success, call `complete_task` with a concise result summary. On a recoverable blocker, call `release_task`. On a real failure, call `fail_task` with a clear failure code and message.

Do not call `extract_action_items`, `accept_action_candidate`, or `ensure_task_from_action` in this
workflow. The user already chose actions in Memova/iOS and sent them to Codex as automation tasks.

## Automation Task Review

When the user asks to review Memova automation tasks without immediately executing them:

1. Run the plugin version check described above.
2. Run the one-time knowledge-base setup reminder check described above.
3. Call `list_automation_tasks` with statuses `pending`, `running`, and `waiting_for_user`,
   `claimable_only=false`, and a reasonable `limit` such as `20`.
   If this MCP tool is unavailable, run `codex mcp list`. If `memova` is listed with Auth
   `Not logged in`, run `python3 plugins/memova/scripts/ensure_mcp_login.py` from the plugin root.
   The helper starts MCP OAuth login and attempts to open one browser authorization URL; the user
   still approves in the browser. If automatic browser opening fails, tell the user to copy the
   printed `authorization_url` into a browser. If the helper reports a `login_error` or
   `manual_login_command`, tell the user to run that command in Windows Terminal/PowerShell or a
   normal shell. After successful login, tell the user to start a new Codex thread if this thread
   still does not expose the Memova MCP tools. If `memova` is not listed, tell the user to
   upgrade/reinstall the Memova plugin and restart Codex.
4. Summarize user-visible task titles/objectives, source note or meeting titles, status, owner,
   practical lease availability, and approval policy. Do not show internal task, note, action,
   lease, event, request, or workspace ids by default; keep them for tool calls and audit only.
   Treat `waiting_for_user` as requiring user attention and as not directly runnable. The absence
   of a separate open approval-request row does not turn a `waiting_for_user` task into an approved
   task; report that as missing/inconsistent confirmation detail and keep the task guarded until
   its context or a later user decision explicitly resumes it.
   When the user asks whether the task can be performed entirely inside Memova, answer **No — it
   is waiting for the user**. Never describe any part of a `waiting_for_user` task as currently
   performable, runnable, executable, allowed, or ready merely because its capability list or
   approval policy would otherwise allow drafting. Missing confirmation metadata is an
   inconsistency to surface, not permission to proceed.
5. Do not claim tasks or write progress for read-only views unless the user asks to run a specific
   task.

When the user asks to execute a specific automation task from a review list, claim only that task,
then call `get_task_context` so the latest events and approval state guide the work.

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

- the user-visible Memova note/task titles used and why they were relevant;
- what was completed or written back;
- what still needs user approval or follow-up; and
- any local verification that was run.

Keep internal ids, claim tokens, hashes, request ids, and raw lifecycle event details out of the
default final response. They remain available for tool calls, logs, audit, and explicit technical
follow-up.
