---
name: memova-menu
description: Show the Memova workflow menu when the user invokes @memova without a specific request, asks to open the Memova menu, chooses a Memova starter prompt, or replies with a numbered Memova menu option. Use this skill to route the user to setup, vault diagnosis, pending tasks, completed actions, ready approvals, or latest final-note workflows without immediately executing a write-heavy workflow.
---

# Memova Menu

Use this skill as the safe Memova entrypoint. It should present concise options first, then route
the user's selection to the correct workflow. Do not run the latest final-note workflow just because
the user typed bare `@memova`.

## Startup Checks

Before showing the menu or dispatching a menu selection, run the plugin version check from the
plugin root:

```bash
python3 plugins/memova/scripts/version_check.py
```

If `version_check.py` returns `should_remind: true`, show its upgrade message and continue.

Before showing the menu or dispatching any non-setup selection, run the one-time knowledge-base
setup reminder:

```bash
python3 plugins/memova/scripts/kb_setup_reminder.py
```

If `kb_setup_reminder.py` returns `should_remind: true`, show its setup message once and keep the
menu visible. If it returns `already_reminded: true`, do not repeat the setup reminder.

## Menu

When the user invokes bare `@memova`, asks for the Memova menu, or the intent is ambiguous, reply
with:

```text
Memova

1. Setup your knowledge base
2. View pending tasks
3. View completed actions
4. Run latest final note workflow
5. Continue pending automation task
6. Diagnose your Memova vault
7. View ready approvals

Reply with a number, or tell me what you want to do.
```

Do not fetch Memova data just to render this menu unless the user asked for counts or details.

## Selection Routing

If the previous assistant message showed the Memova menu and the user replies with only a number or
one of the option names, treat it as a Memova menu selection even if the new user message does not
repeat `@memova`.

- `1` or "setup": Follow `plugins/memova/skills/memova-vault-setup/SKILL.md`.
- `2` or "pending tasks": Call `list_pending_tasks`, then call
  `list_action_items` with statuses `accepted`, `planned`, and `in_progress` when the user wants
  action items rather than automation tasks. Summarize ids, titles, source meetings, status, and the
  safest next action. Do not claim or execute tasks unless the user explicitly asks.
- `3` or "completed actions": Call `list_action_items` with status `done`. Summarize ids, titles,
  source meetings when present, completion dates when available, and any visible follow-up state.
  If the user asks for completed Codex automation execution history, explain that this plugin
  currently exposes completed action items through MCP; detailed completed automation history may
  require a future backend MCP list-by-status tool.
- `4` or "latest final note": Follow the latest final-note workflow in
  `plugins/memova/skills/memova-workflow/SKILL.md`.
- `5` or "continue": Follow the pending task workflow in
  `plugins/memova/skills/memova-workflow/SKILL.md`; claim one task at a time.
- `6` or "diagnose": Follow `plugins/memova/skills/memova-vault-diagnose/SKILL.md`.
- `7` or "approvals": Call `list_ready_approvals` and summarize ready approval responses. If a
  response unblocks a task, ask before claiming or continuing that task.

## Safety

- Check that Memova MCP tools are available and authenticated before calling them. If auth is
  missing, tell the user to complete Memova OAuth MCP login and stop.
- Setup, diagnosis repair, task claiming, task execution, external writes, and destructive local
  changes require the approval rules in the target workflow skill.
- Keep menu responses short. For list views, show enough information for the user to choose a next
  step, not the full raw payload.
