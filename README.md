# Memova Codex Plugin

Codex plugin marketplace for Memova.

This plugin bundles:

- the Memova OAuth MCP server at `https://api.memova.ai/mcp`,
- the `memova-menu` skill for a lightweight `@memova` workflow menu,
- the `memova-personal-manual` skill for bounded history analysis and atomic Personal Manual Note
  publication,
- the `memova-knowledge` skill for bounded Knowledge V5 retrieval and reviewed Knowledge Entries,
- the `memova-workflow` skill for reviewing and running existing Codex automation tasks,
- the `memova-vault-setup` skill for iCloud-first Memova knowledge-base setup,
- the `memova-vault-diagnose` skill for validating and repairing a Memova V2/V3 managed root,
- the `memova-explicit-import` skill for bounded user-selected text with preview and local
  Restricted Data filtering,
- Memova starter prompts and plugin presentation metadata.

Version `1.8.3` treats an explicit Personal Manual generation request as authorization to run the
bounded workflow disclosed on Memova's product surface, so it no longer repeats a source-scope or
publication confirmation. It loads the `personal_manual_generation_v1` contract from Memova MCP
before reading history, so the Codex Plugin and direct-MCP clients share one scoring, writing,
privacy, authorization, and upload contract. It preserves the `1.8.1` bounded `-15` calibration
after sparse-evidence shrink and the 0–100 score contract. Version `1.8.0` added the
Personal Manual Skill on top of the reviewed first-class V5 Knowledge Entry
contract from `1.7.0`. Personal Manual history access is foreground-only, bounded by one explicit
generation request, and locally filtered to user/assistant text. The Skill uploads only the final Markdown,
validated public document data, and private aggregate metadata; it never uploads source history.
The 1.8.0 preparer accepts exactly the 16 canonical Work Archetype names from the generation
contract and rejects Markdown/CSV Archetype mismatches before any MCP upload.
The public package under `plugins/memova/` contains no Collector runtime, App Server history reader,
Hook, or scheduler installer. Exact-task selected import remains separately previewed and approved,
removes detected Restricted Data, and a successful selected import
both receives a durable archive ACK and deterministically commits the exact approved text as a
canonical Knowledge V5 Codex Session; search rollout and semantic enrichment remain separate.

Independent complete-history collection is maintained separately under top-level `collector/`; it
is not part of the marketplace plugin path, public Plugin menu, starter prompts, or installation.
Collector remains independently versioned at `1.6.0` because this `1.8.3` public Plugin release
does not change Collector code, consent, transport, or installer bytes.

## Should This Repo Be Public?

For normal beta users, yes: make this repository public, or put it somewhere every installer can access.

Codex installs third-party plugins by reading a Git marketplace source. A public GitHub repo is the simplest path because this command works without extra GitHub setup:

```bash
codex plugin marketplace add gxyfred/memova-codex-plugin
```

A private repo can also work for internal testing, but every user must have GitHub access to the repo and working Git credentials on the machine where Codex runs. For private repos, an SSH URL is often easier after the user has GitHub SSH access configured:

```bash
codex plugin marketplace add git@github.com:gxyfred/memova-codex-plugin.git
```

This repo does not contain Memova user data or OAuth tokens.

## Release Coordination

The plugin repository's `main` branch is treated as the installable/updateable plugin line. Do not
merge knowledge-base setup, validator, or repair-flow changes into plugin `main` until the matching
backend contract has already landed on the Memova backend `main` branch and is ready for the
app/plugin clients that will consume it.

During backend development, keep these plugin changes on a separate `codex/` feature branch. This
prevents a plugin update from exposing a local file-tree or validation contract before the backend
API and iOS handoff are ready.

Development remains isolated on a `codex/` feature branch until the matching backend contract is
ready. Existing V2/V3 tools remain present during the staged transition; V5 does not dual-write V3.

## Requirements

- Codex CLI or Codex app installed and signed in.
- A Memova account.
- Access to this GitHub repository.
- Network access to `https://api.memova.ai/mcp` for public Plugin workflows.

## Quick Start

From Codex CLI, add the marketplace source, then install the Memova plugin from that marketplace:

```bash
codex plugin marketplace add gxyfred/memova-codex-plugin
codex plugin add memova@memova-codex-plugin
```

The first command only adds the marketplace source. The second command installs the actual
`memova` plugin. `codex plugin list` is optional; use it only when you want to inspect available
plugins or confirm the installed status.

Open Codex:

```bash
codex
```

Open the plugin directory:

```text
/plugins
```

Choose the `Memova Codex Plugins` marketplace, then install `Memova`.

The `/plugins` UI is an alternative to `codex plugin add memova@memova-codex-plugin`; you do not
need both.

Start a new thread after installation so Codex loads the plugin.

## Connect Memova OAuth MCP

Memova's setup and automation workflows require the bundled MCP server to be authenticated before
Codex can expose its tools. The plugin normally starts this login automatically the first time a
setup or automation workflow needs Memova MCP and the local server is `Not logged in`. It runs:

```bash
codex mcp login memova --scopes notes.read,personal_manual.write,automation.read,automation.write,knowledge.read,knowledge.write
```

and attempts to open one browser authorization URL. The user still approves Memova OAuth in the
browser. If Windows, Linux, or a Codex sandbox blocks automatic browser launch, the helper prints a
copyable `authorization_url`; paste that URL into a browser to finish OAuth. After OAuth succeeds,
restart Codex or start a new thread if the current thread still does not expose the Memova MCP
tools; Codex does not refresh MCP tool availability mid-thread.

The plugin cannot currently open a new Codex Desktop thread and inject the next prompt by itself.
It can run the OAuth helper automatically, then show the exact next `@memova` prompt for a fresh
thread. Codex CLI has `codex fork` and `codex exec` for terminal workflows, but knowledge-base setup
is intentionally interactive because it asks before local file writes.

You can also run the bundled helper directly from the plugin root:

```bash
python3 plugins/memova/scripts/ensure_mcp_login.py
```

If the helper cannot start `codex` because of WindowsApps or sandbox permissions, run the same MCP
login command directly in Windows Terminal or PowerShell:

```powershell
codex mcp login memova --scopes notes.read,personal_manual.write,automation.read,automation.write,knowledge.read,knowledge.write
```

You can verify the state with:

```bash
codex mcp list
```

The `memova` row should be enabled and logged in. If it says `Not logged in`, MCP-backed setup and
automation tools such as `list_pending_knowledge_base_setups` will not be exposed in Codex yet.
Avoid starting a second manual `codex mcp login` while a Memova authorization tab is already open.

## Use The Plugin

In Codex, type:

```text
@memova
```

Codex should open a short Memova menu:

```text
1. Create or update my Personal Manual
2. Search and use my Knowledge V5
3. Create or update a Knowledge Entry
4. Import selected content
5. Review my automation tasks
6. Run latest note automation tasks
7. Legacy V2/V3 vault setup or diagnosis
```

Reply with a number, or select one of the plugin starter prompts:

```text
Create and publish my Memova Personal Manual.
Search and use my Memova Knowledge V5.
Create or update a reviewed Knowledge Entry in Memova.
```

You can still ask directly:

```text
@memova Run latest note automation tasks.
@memova Review my automation tasks.
@memova Import this selected content.
@memova Set up legacy V2/V3 vault.
```

The menu is the safe default entrypoint. It does not run a write-heavy workflow just because the
user typed bare `@memova`; it routes the user to Knowledge V5 retrieval/proposals,
Personal Manual generation, selected-content import, read-only automation task review,
latest-note automation task execution, or explicit legacy vault tools.

## Create A Personal Manual

Start with `@memova 个人说明书`. The explicit request starts the disclosed bounded workflow
without another confirmation. It reads up to 50 accessible Codex/ChatGPT conversations and keeps the
Markdown, scores CSV, and source-count CSV locally; only the validated Markdown, public document,
four dimensions, Archetype, overall confidence, and aggregate source statistics are sent through
MCP. Memova renders the script-free HTML and returns the stable public URL. Raw conversation text
and facet scores are never uploaded.

Before reading history, Plugin 1.8.3 calls `get_personal_manual_generation_contract` and requires
`personal_manual_generation_v1`. The MCP contract is authoritative; an absent or unsupported
contract stops the workflow instead of silently using stale local scoring rules. Bare `@memova`,
setup/login-only requests, and informational or ambiguous Personal Manual mentions do not start
history access or publication.

The menu itself does not fetch Memova data. MCP-backed selections require the Memova MCP login above.
If Codex says setup or automation MCP tools are unavailable, check `codex mcp list`; `Not logged in`
means the OAuth step has not completed for this Codex install. The setup/workflow skills should run
the bundled login helper instead of asking the user to type the command manually.

The latest-note automation workflow does not extract new actions from a final note. It reads
existing `automation_tasks` that the user already sent to Codex from Memova/iOS, claims one safe
task at a time, asks before approval-required work, executes safe tasks when the current workspace
is appropriate, and writes progress/results back to Memova.

The legacy V2/V3 options retain the one-time local vault reminder under
`~/.cache/memova-codex-plugin/`. It no longer blocks Knowledge V5 or automation workflows.

The plugin also checks for newer Memova plugin releases at most once per day. If a newer version is
available, it reminds the user to upgrade, then repeats that reminder at most once every 7 days for
the same latest version.

## Legacy V2/V3 Vault Compatibility

The knowledge-base setup flow is designed for users who already completed the Memova iOS setup step and marked setup ready for Codex.

In Codex, run:

```text
@memova Set up knowledge base.
```

Codex will:

1. Pull the ready setup package from Memova through MCP.
2. Discover likely iCloud Drive and existing vault locations on the Mac.
3. Inspect an existing vault lightly if the setup package or user provides a path, then target the
   root-level `Memova/` managed sub-knowledge-base.
4. Build a dry-run file operation plan.
5. Ask before writing files.
6. Create the V2 or V3 root requested by the current setup package, either as a new vault or a
   scoped `Memova/` managed root inside the approved existing vault root. V3 directories, contents,
   hashes, byte sizes, write modes, and preservation rules come only from backend
   `setup_operations`; the plugin does not hardcode the V3 tree.
7. Write the backend/plugin contract files for humans, iOS, and agents. Meeting packets still use
   Memova Inbox Packet Format v1
   under `inbox/meetings/`.
   Existing user files are not overwritten, but setup identity manifests are refreshed when the user
   reuses an old Memova directory so iOS sees the current setup session ids.
8. Validate the Memova managed-root manifest, setup identity, setup documentation, schema files, and
   required metadata files.
9. Report success or failure back to Memova through MCP, including
   `memova_input_root_relative_path`.

If multiple old setup sessions are still ready/running, Codex asks which one to use. It shows the
unselected session ids and obtains adjacent confirmation before marking any of them failed with
`failure_code=setup.superseded_by_selected_session`; otherwise they remain unchanged.

Before reporting success, the helper returns `identity_validation`. Codex must only call
`complete_knowledge_base_setup` when that status is `ok`; otherwise the local manifest files do not
match the backend setup session and iOS folder binding can fail.

Local validation alone is not setup completion. Codex must not report "Memova knowledge base setup
is complete" unless `complete_knowledge_base_setup` succeeds for the current backend setup session.
If a thread can validate files but cannot access the Memova setup MCP tools, the correct result is:
the local folder is valid, but backend setup is incomplete and iOS may not be able to bind the
current setup session.

For final setup validation, run:

```bash
python3 scripts/validate_memova_vault.py \
  --path "<approved-target-path>" \
  --setup-json "/tmp/memova-setup.json" \
  --require-setup-identity
```

Only after `complete_knowledge_base_setup` succeeds may Codex mark the local reminder complete:

```bash
python3 plugins/memova/scripts/kb_setup_reminder.py \
  --mark-complete \
  --backend-completed \
  --setup-session-id "<setup_session_id>" \
  --vault-path "<approved-target-path>"
```

If Codex cannot call the Memova setup MCP tools or cannot retrieve a valid setup package, setup
must stop before any local file plan/create command. The local filesystem helper requires
`--setup-json` specifically to avoid silently creating a default vault when the app already supplied
setup path hints.

For a new iCloud vault, the usual Mac target path is:

```text
~/Library/Mobile Documents/com~apple~CloudDocs/Memova Vault
```

If the setup package includes `target_path_hints.desired_input_folder_name`, that value becomes the
new vault folder name. For example `desired_input_folder_name: "Test111"` maps to:

```text
~/Library/Mobile Documents/com~apple~CloudDocs/Test111
```

If the user connects an old Obsidian or Markdown vault, Codex preserves the user's structure and
creates only a root-level `Memova/` managed sub-knowledge-base after user approval, for example:

```text
~/Library/Mobile Documents/com~apple~CloudDocs/Existing Obsidian Vault/Memova
```

After Codex creates the vault/managed root, the iOS app should ask the user to select the same folder
or an ancestor folder through Files. The setup result includes `ios_folder_binding_hints`, so iOS
can use iCloud-relative manifest paths and the expected manifest ids to find the right
folder after authorization. Do not rely on the Mac absolute path inside iOS; the manifest identifies
the binding.

Example new-vault hints:

```json
{
  "icloud_relative_input_root_path": "Test111",
  "input_root_manifest_relative_path": "Test111/_memova/manifest.json",
  "expected_input_root_manifest_id": "memova-input-root-..."
}
```

## File Tree Created By Setup

The actual file-tree implementation lives in:

```text
plugins/memova/skills/memova-vault-setup/scripts/memova_vault_lib.py
```

For a V2 setup, the compatibility tree below is created locally. The folder name is illustrative; a
setup package can request a different name such as `Test111`. For V3, treat the backend package's
`vault_contract.memova_managed_root.setup_operations` as canonical; this README intentionally does
not duplicate a V3 file tree that could drift from the backend contract.

```text
Memova Vault/
  index.md
  README.md
  AGENTS.md
  log.md
  inbox/
    index.md
    README.md
    meetings/
    captures/
    imports/
    activity/
  wiki/
    index.md
    people/
    organizations/
    topics/
    decisions/
    processes/
    references/
  projects/
    index.md
  daily/
    index.md
  outputs/
    index.md
    reports/
    briefs/
    specs/
    decks/
    assets/
  archive/
    index.md
  schemas/
    index.md
    README.md
    okf-concept.schema.md
    memova-root.schema.md
    meeting-packet.schema.md
    promotion.schema.md
  _memova/
    manifest.json
    root.json
    tree_manifest.json
    sync_state.json
    source_index.json
    promotion_index.json
    repair_state.json
```

For an existing vault, Codex creates only the root-level Memova managed root:

```text
Existing User Vault/
  Memova/
    index.md
    README.md
    AGENTS.md
    inbox/
      meetings/
      captures/
      imports/
      activity/
    wiki/
    projects/
    daily/
    outputs/
    schemas/
    archive/
    _memova/
      manifest.json
      root.json
      tree_manifest.json
      sync_state.json
      source_index.json
      promotion_index.json
      repair_state.json
```

Memova writes raw meeting packets only under `inbox/meetings/` in the managed root. It does not
classify meetings into projects, update wiki pages, or reorganize an existing knowledge base during
setup.

Setup does not pre-create concrete meeting packet folders. After meetings end, the iOS app writes
packets under `inbox/meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/` using the backend sync package.
The setup README, AGENTS, INDEX, and schema files describe that future packet shape:
`README.md`, `manifest.json`, `sources.md`, `note.md`, `packet.json`, `promotion.json`, and
`assets/manifest.json` plus optional binary assets.

## Diagnose Or Repair A Memova Vault

If setup completed but the iOS app cannot verify the folder, or meeting-to-vault sync cannot write,
run:

```text
@memova Diagnose your Memova vault.
```

Codex will ask for the Mac path if needed, then use deterministic helper scripts to inspect and
validate the folder. The diagnosis checks required Memova README/AGENTS/schema files, manifests,
machine state files, managed-root relative paths, and lightweight `Memova/` binding candidates. If
files are missing, Codex can show a repair plan, but it must ask before writing anything.
If older setup docs exist but are empty or too thin, Codex can repair them only after explicit user
approval with `--overwrite-machine-files`; raw meeting packet files are still not overwritten by
that repair mode.

The underlying script can be run directly during development. V3 repair requires a current backend
setup/repair package; without one, diagnosis remains read-only and refuses to invent repair files:

```bash
python3 plugins/memova/skills/memova-vault-setup/scripts/diagnose_memova_vault.py \
  --path "/path/to/Memova Vault or managed root" \
  --setup-json "/tmp/memova-setup.json" \
  --repair-plan
```

## Import Explicitly Selected Content

Start with `@memova Import this selected content.` The public Plugin accepts pasted/current excerpt
text, an attached text resource, an exact task/date-range export already supplied by the
client/user, or one exact `codex://threads/<uuid>` URL the user explicitly asks to summarize/import.
That URL authorizes only `codex_app__read_thread` for the named task, never task listing or
neighboring-task access. A guessed/bare id or date range alone does not authorize history access.

Before upload, the Plugin produces a bounded local preview with source label, exact byte/character
counts, original/sanitized hashes, and Restricted Data finding counts. The user approves the exact
sanitized bytes immediately before the MCP write. The Plugin never uses task-list APIs for an exact
URL import, Codex internal JSONL/SQLite, filesystem scans, or UI scraping as a fallback.

## What The Menu And Workflow Do

When triggered, the bundled `memova-menu` skill tells Codex to:

1. Run the low-frequency plugin version check.
2. Show a numbered menu for Personal Manual generation, selected-content import, automation task
   review, latest-note automation task execution, and explicit legacy vault compatibility.
3. Run the one-time knowledge-base setup reminder only after a legacy vault option is selected.
4. Treat a simple numeric reply like `1` or `2` as the selected Memova action in the current
   thread.
5. Keep automation task review read-only unless the user explicitly asks to execute a task.

When triggered, the bundled `memova-workflow` skill tells Codex to:

1. Read existing Memova automation tasks through MCP.
2. For latest-note execution, call `list_latest_note_automation_tasks` and use only tasks already
   linked to the latest ready note's meeting.
3. Ask before work that needs approval, such as external messages, calendars, purchases, destructive changes, production deploys, secrets, or unclear repo context.
4. Claim matching Memova automation tasks when appropriate.
5. Execute safe work in the current Codex workspace.
6. Write progress, completion, release, approval, or failure state back to Memova through MCP.

## What This Is

This repository is a Codex plugin marketplace. It does not run a backend service and does not replace the Memova MCP server. The backend MCP endpoint remains `https://api.memova.ai/mcp`.

## Update

To pull the latest marketplace/plugin changes:

```bash
codex plugin marketplace upgrade memova-codex-plugin
```

Then restart Codex or start a new thread if the plugin UI does not refresh.

Installed third-party plugins should not be treated as automatically updated. Memova workflows
include a low-frequency version check and may show this upgrade command when the installed plugin is
behind.

## Troubleshooting

If `codex plugin marketplace add gxyfred/memova-codex-plugin` fails:

- Confirm the repo is public, or confirm your GitHub credentials can clone it.
- Try the full HTTPS URL:

```bash
codex plugin marketplace add https://github.com/gxyfred/memova-codex-plugin.git
```

- For private access, try the SSH URL after configuring GitHub SSH:

```bash
codex plugin marketplace add git@github.com:gxyfred/memova-codex-plugin.git
```

If `@memova` does not appear:

- Restart Codex after installing the plugin.
- Confirm both install steps completed:
  `codex plugin marketplace add gxyfred/memova-codex-plugin` and
  `codex plugin add memova@memova-codex-plugin`.
- Open `/plugins` and confirm `Memova` is installed and enabled.
- Start a new thread after installation.

If Memova tools are unavailable:

- Run `python3 plugins/memova/scripts/ensure_mcp_login.py` from the plugin root, using the same
  Memova account as the iOS app setup.
- If automatic browser opening fails, copy the printed `authorization_url` into a browser. If the
  helper cannot execute `codex` because of WindowsApps or sandbox permissions, run
`codex mcp login memova --scopes notes.read,personal_manual.write,automation.read,automation.write,knowledge.read,knowledge.write`
  directly in Windows Terminal or PowerShell, then restart Codex or start a new thread.
- If setup packages exist in the app but Codex sees none, the most likely cause is that Codex OAuth
  is connected to a different Memova account than the iOS app.
- Confirm the Memova account has access to the expected notes and actions.
- Confirm the MCP endpoint is reachable from the machine running Codex.
- If setup is the current workflow, do not use local fallback paths. Start a new Codex thread or
  restart Codex after installing/enabling the plugin so the setup MCP tools are loaded, then retry.

## Development

Validate JSON files:

```bash
python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
python3 -m json.tool plugins/memova/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/memova/.mcp.json >/dev/null
```

Validate skill metadata and helper scripts:

```bash
ruby -e 'require "yaml"; YAML.load_file("plugins/memova/skills/memova-menu/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-personal-manual/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-workflow/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-vault-setup/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-vault-diagnose/agents/openai.yaml"); puts "yaml ok"'
python3 -m py_compile plugins/memova/scripts/*.py plugins/memova/skills/memova-personal-manual/scripts/*.py plugins/memova/skills/memova-vault-setup/scripts/*.py
python3 plugins/memova/skills/memova-vault-setup/scripts/create_memova_vault.py discover
python3 plugins/memova/skills/memova-vault-setup/scripts/setup_fixture_harness.py --json
python3 plugins/memova/scripts/ensure_mcp_login.py --check-only
python3 plugins/memova/scripts/version_check.py --force
python3 plugins/memova/scripts/kb_setup_reminder.py
```

Inspect the marketplace locally:

```bash
codex plugin marketplace add .
```
