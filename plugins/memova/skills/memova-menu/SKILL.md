---
name: memova-menu
description: Show the current Memova workflow menu when the user invokes @memova without a specific request, asks to open the Memova menu, chooses a Memova starter prompt, or replies with a numbered Memova menu option. Route to Personal Manual, Knowledge V5, explicit import, automation, or legacy vault tools without starting a write-heavy workflow.
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

Run the legacy knowledge-base setup reminder only after the user selects legacy option 6. It
must not block Knowledge V5 or automation workflows:

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

1. Create or update my Personal Manual
2. Search and use my Knowledge V5
3. Create or update a Knowledge Entry
4. Import selected content
5. Review my automation tasks
6. Run latest note automation tasks
7. Legacy V2/V3 vault setup or diagnosis

Reply with a number, or tell me what you want to do.
```

Do not fetch Memova data just to render this menu unless the user asked for counts or details.

## Selection Routing

If the previous assistant message showed the Memova menu and the user replies with only a number or
one of the option names, treat it as a Memova menu selection even if the new user message does not
repeat `@memova`.

- `1` or "Personal Manual": Follow
  `plugins/memova/skills/memova-personal-manual/SKILL.md`. Ask once for source-scope confirmation;
  generation, upload, and link publication then continue automatically.
- `2`, "search", "knowledge", or "Knowledge V5": Follow the read-only workflow in
  `plugins/memova/skills/memova-knowledge/SKILL.md`.
- `3`, "propose", "Knowledge Entry", or "knowledge update": Follow the proposal workflow in
  `plugins/memova/skills/memova-knowledge/SKILL.md`. Show the exact candidate and obtain adjacent
  approval before calling `apply_knowledge_entry_proposal`.
- `4`, "import", or "selected content": Follow
  `plugins/memova/skills/memova-explicit-import/SKILL.md`. The user must still approve the exact
  sanitized preview before the MCP write.
- `5` or "automation tasks": Follow the automation task review workflow in
  `plugins/memova/skills/memova-workflow/SKILL.md`. It should call `list_automation_tasks` with
  statuses `pending`, `running`, and `waiting_for_user`, `claimable_only=false`, and a reasonable
  limit such as `20`. Summarize user-visible task titles/objectives, status, owner, source
  note/meeting titles when present, practical availability, and approval state. Keep internal ids
  and raw lease details out of the default response. Do not claim or execute tasks unless the user
  explicitly asks.
- `6` or "latest note": Follow the latest-note automation task workflow in
  `plugins/memova/skills/memova-workflow/SKILL.md`. This workflow must only use existing
  automation tasks linked to the latest ready note's meeting. It must not call
  `extract_action_items`, `accept_action_candidate`, or `ensure_task_from_action`.
- `7` or "legacy vault": Ask whether the user wants setup or diagnosis. Run the one-time legacy
  reminder, then follow `plugins/memova/skills/memova-vault-setup/SKILL.md` for setup or
  `plugins/memova/skills/memova-vault-diagnose/SKILL.md` for diagnosis.
- Do not run Memova MCP login merely to show the menu.

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
