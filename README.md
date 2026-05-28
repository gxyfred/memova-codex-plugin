# Memova Codex Plugin

Codex plugin marketplace for Memova.

This plugin bundles:

- the Memova OAuth MCP server at `https://api.memova.ai/mcp`,
- the `memova-menu` skill for a lightweight `@memova` workflow menu,
- the `memova-workflow` skill for reviewing and running existing Codex automation tasks,
- the `memova-vault-setup` skill for iCloud-first Memova knowledge-base setup,
- the `memova-vault-diagnose` skill for validating and repairing a Memova vault/input root,
- Memova starter prompts and plugin presentation metadata.

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

This repo does not contain Memova user data or OAuth tokens. It only contains plugin metadata, workflow instructions, icons, and the public MCP endpoint URL. Each user's Memova data remains protected by Memova OAuth during MCP login.

## Requirements

- Codex CLI or Codex app installed and signed in.
- A Memova account.
- Access to this GitHub repository.
- Network access to `https://api.memova.ai/mcp`.

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
codex mcp login memova --scopes notes.read,actions.read,actions.write,automation.read,automation.write
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
codex mcp login memova --scopes notes.read,actions.read,actions.write,automation.read,automation.write
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
1. Set up knowledge base
2. Review my automation tasks
3. Run latest note automation tasks
4. Diagnose knowledge base
```

Reply with a number, or select one of the plugin starter prompts:

```text
Open Memova menu.
Set up knowledge base.
Review my automation tasks.
Run latest note automation tasks.
Diagnose knowledge base.
```

You can still ask directly:

```text
@memova Run latest note automation tasks.
@memova Review my automation tasks.
@memova Diagnose knowledge base.
```

The menu is the safe default entrypoint. It does not run a write-heavy workflow just because the
user typed bare `@memova`; it routes the user to setup, read-only automation task review,
latest-note automation task execution, or vault diagnosis.

The menu itself does not fetch Memova data. MCP-backed selections require the Memova MCP login above.
If Codex says setup or automation MCP tools are unavailable, check `codex mcp list`; `Not logged in`
means the OAuth step has not completed for this Codex install. The setup/workflow skills should run
the bundled login helper instead of asking the user to type the command manually.

The latest-note automation workflow does not extract new actions from a final note. It reads
existing `automation_tasks` that the user already sent to Codex from Memova/iOS, claims one safe
task at a time, asks before approval-required work, executes safe tasks when the current workspace
is appropriate, and writes progress/results back to Memova.

On the first non-setup Memova workflow, the plugin checks whether a Memova knowledge-base vault is
already present on the Mac. If not, it shows one setup reminder, records that reminder locally under
`~/.cache/memova-codex-plugin/`, and does not repeat it on later workflows. Users can still start
setup explicitly with `@memova Set up knowledge base.`

The plugin also checks for newer Memova plugin releases at most once per day. If a newer version is
available, it reminds the user to upgrade, then repeats that reminder at most once every 7 days for
the same latest version.

## Set Up A Memova Knowledge Base

The knowledge-base setup flow is designed for users who already completed the Memova iOS setup step and marked setup ready for Codex.

In Codex, run:

```text
@memova Set up knowledge base.
```

Codex will:

1. Pull the ready setup package from Memova through MCP.
2. Discover likely iCloud Drive and existing vault locations on the Mac.
3. Inspect an existing vault lightly if the setup package or user provides a path, then suggest the
   best raw-input folder such as `Inbox`, `00_Inbox`, `Sources`, or `Resources`.
4. Build a dry-run file operation plan.
5. Ask before writing files.
6. Create either a new empty Memova vault skeleton with `inbox/memova/`, or only a scoped Memova
   input root inside the approved existing vault folder.
7. Write non-empty README, AGENTS, schema, manifest, and sync-state files that explain the raw-input
   contract for humans, iOS, and agents. The input root uses Memova Inbox Packet Format v1.
8. Validate the Memova input-root manifest, setup documentation, schema files, and required metadata
   files.
9. Report success or failure back to Memova through MCP, including
   `memova_input_root_relative_path`.

If multiple old setup sessions are still ready/running, Codex asks which one to use, then marks the
unselected setup sessions failed with `failure_code=setup.superseded_by_selected_session` so they do
not keep showing up in future setup runs.

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

If the user connects an old Obsidian or Markdown vault, Codex preserves the user's structure. It
lightly scans for the best raw-input folder and creates only a scoped Memova input root after user
approval, for example:

```text
~/Library/Mobile Documents/com~apple~CloudDocs/Existing Obsidian Vault/00_Inbox/Memova
```

After Codex creates the vault/input root, the iOS app should ask the user to select the same folder
or an ancestor folder through Files. The setup result includes `ios_folder_binding_hints`, so iOS
can use iCloud-relative manifest paths and the expected input-root manifest id to find the right
folder after authorization. Do not rely on the Mac absolute path inside iOS; the manifest identifies
the binding.

Example new-vault hints:

```json
{
  "icloud_relative_input_root_path": "Test111/inbox/memova",
  "input_root_manifest_relative_path": "Test111/inbox/memova/_memova/manifest.json",
  "expected_input_root_manifest_id": "memova-input-root-..."
}
```

## File Tree Created By Setup

The actual file-tree implementation lives in:

```text
plugins/memova/skills/memova-vault-setup/scripts/memova_vault_lib.py
```

For a new vault, Codex creates an empty Memova vault skeleton and the Memova input root. The folder
name shown here is illustrative; a setup package can request a different new-vault folder such as
`Test111`.

```text
Memova Vault/
  README.md
  AGENTS.md
  inbox/
    README.md
    memova/
      README.md
      AGENTS.md
      INDEX.md
      schemas/
        meeting_packet.schema.md
        manifest.schema.md
        packet.schema.md
        asset.schema.md
        promotion.schema.md
      meetings/
      _memova/
        manifest.json
        input_root.json
        sync_state.json
        source_index.json
  sources/
    README.md
  wiki/
    README.md
  projects/
    README.md
  daily/
    README.md
  outputs/
    README.md
  archive/
    README.md
  schemas/
    README.md
  _memova/
    manifest.json
    vault_mapping.json
    sync_state.json
```

For an existing vault, Codex creates only the approved Memova input root, usually something like:

```text
Existing User Vault/
  00_Inbox/
    Memova/
      README.md
      AGENTS.md
      INDEX.md
      schemas/
        meeting_packet.schema.md
        manifest.schema.md
        packet.schema.md
        asset.schema.md
        promotion.schema.md
      meetings/
      _memova/
        manifest.json
        input_root.json
        sync_state.json
        source_index.json
```

Memova V1 writes raw meeting packets only under the Memova input root. It does not classify
meetings into projects, update wiki pages, or reorganize an existing knowledge base.

Setup does not pre-create concrete meeting packet folders. After meetings end, the iOS app writes
packets under `meetings/YYYY/MM/YYYY-MM-DD-<slug>-<meeting_id>/` using the backend sync package.
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
machine state files, input-root relative paths, and lightweight raw-input folder candidates. If
files are missing, Codex can show a repair plan, but it must ask before writing anything.
If older setup docs exist but are empty or too thin, Codex can repair them only after explicit user
approval with `--overwrite-machine-files`; raw meeting packet files are still not overwritten by
that repair mode.

The underlying script can be run directly during development:

```bash
python3 plugins/memova/skills/memova-vault-setup/scripts/diagnose_memova_vault.py \
  --path "/path/to/Memova Vault or input root" \
  --repair-plan
```

## What The Menu And Workflow Do

When triggered, the bundled `memova-menu` skill tells Codex to:

1. Run the low-frequency plugin version check.
2. Run the one-time knowledge-base setup reminder check.
3. Show a numbered menu for setup, automation task review, latest-note automation task execution,
   and vault diagnosis.
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
  `codex mcp login memova --scopes notes.read,actions.read,actions.write,automation.read,automation.write`
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
ruby -e 'require "yaml"; YAML.load_file("plugins/memova/skills/memova-menu/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-workflow/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-vault-setup/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-vault-diagnose/agents/openai.yaml"); puts "yaml ok"'
python3 -m py_compile plugins/memova/scripts/*.py plugins/memova/skills/memova-vault-setup/scripts/*.py
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
