---
name: memova-menu
description: Show the Memova workflow menu when the user invokes @memova without a specific request, asks to open the Memova menu, chooses a Memova starter prompt, or replies with a numbered Memova menu option. Use this skill to route the user to setup, automation task review, latest-note automation task execution, vault diagnosis, or explicit private conversation-sync management without immediately executing a write-heavy workflow.
---

# Memova Menu

Use this skill as the safe Memova entrypoint. It should present concise options first, then route
the user's selection to the correct workflow. Do not run latest-note automation tasks just because
the user typed bare `@memova`.

## Startup Checks

Do not check Memova MCP authentication or call Memova MCP tools just to render the bare `@memova`
menu. The menu must be lightweight and should not open the browser/OAuth flow by itself. OAuth is
triggered once the user selects an MCP-backed option such as setup, automation task review, or
latest-note task execution.

Before showing the menu or dispatching a menu selection, run the plugin version check from the
plugin root:

```bash
python3 plugins/memova/scripts/version_check.py
```

If `version_check.py` returns `should_remind: true`, show its upgrade message and continue.

Before showing the menu or dispatching knowledge-base or automation selections 2-4, run the one-time
knowledge-base setup reminder. Conversation-sync selection 5 is independent and must not be blocked
by knowledge-base readiness:

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

1. Set up knowledge base
2. Review my automation tasks
3. Run latest note automation tasks
4. Diagnose knowledge base
5. Set up private Codex conversation sync

Reply with a number, or tell me what you want to do.
```

Do not fetch Memova data just to render this menu unless the user asked for counts or details.

## Selection Routing

If the previous assistant message showed the Memova menu and the user replies with only a number or
one of the option names, treat it as a Memova menu selection even if the new user message does not
repeat `@memova`.

- `1` or "setup": Follow `plugins/memova/skills/memova-vault-setup/SKILL.md`.
- `2` or "automation tasks": Follow the automation task review workflow in
  `plugins/memova/skills/memova-workflow/SKILL.md`. It should call `list_automation_tasks` with
  statuses `pending`, `running`, and `waiting_for_user`, `claimable_only=false`, and a reasonable
  limit such as `20`. Summarize task ids, objective, status, source note/meeting context when
  present, lease state, and approval state. Do not claim or execute tasks unless the user
  explicitly asks.
- `3` or "latest note": Follow the latest-note automation task workflow in
  `plugins/memova/skills/memova-workflow/SKILL.md`. This workflow must only use existing
  automation tasks linked to the latest ready note's meeting. It must not call
  `extract_action_items`, `accept_action_candidate`, or `ensure_task_from_action`.
- `4` or "diagnose": Follow `plugins/memova/skills/memova-vault-diagnose/SKILL.md`.
- `5`, "conversation sync", or "collector": Follow
  `plugins/memova/skills/memova-conversation-sync/SKILL.md`. Selecting this menu item is an explicit
  request to open the workflow, but it is not consent to install files, read/upload history,
  authorize Collector OAuth, write or activate a scheduler, delete remote data, or trust Hooks.
  The target Skill must ask at those boundaries. Do not run the Memova MCP login helper for this
  selection; Collector OAuth is separate.

## Safety

- Do not perform a separate Memova MCP auth check for the menu itself. For MCP-backed selections,
  follow the target workflow's MCP login checks. If the needed MCP tools are unavailable and
  `codex mcp list` shows `memova` Auth `Not logged in`, run
  `python3 plugins/memova/scripts/ensure_mcp_login.py` from the plugin root. The helper starts MCP
  OAuth login and attempts to open one browser authorization URL; the user still approves in the
  browser. If automatic browser opening fails, tell the user to copy the printed
  `authorization_url` into a browser. If the helper reports a `login_error` or
  `manual_login_command`, tell the user to run that command in Windows Terminal/PowerShell or a
  normal shell. After successful login, tell the user to start a new Codex thread if this thread
  still does not expose the Memova MCP tools.
- Setup, diagnosis repair, automation task claiming, task execution, external writes, and destructive local
  changes require the approval rules in the target workflow skill.
- Keep menu responses short. For list views, show enough information for the user to choose a next
  step, not the full raw payload.
