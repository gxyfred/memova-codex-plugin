# Memova Codex Plugin

Codex plugin marketplace for Memova.

This plugin bundles:

- the Memova OAuth MCP server at `https://api.memova.ai/mcp`,
- the `memova-workflow` skill for one-click final-note workflows,
- the `memova-vault-setup` skill for iCloud-first Memova knowledge-base setup,
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

From Codex CLI, add this marketplace:

```bash
codex plugin marketplace add gxyfred/memova-codex-plugin
```

Open Codex:

```bash
codex
```

Open the plugin directory:

```text
/plugins
```

Choose the `Memova Codex Plugins` marketplace, then install `Memova`.

Start a new thread after installation so Codex loads the plugin.

## Connect Memova OAuth MCP

If Codex asks for MCP authentication, complete the Memova OAuth flow. The bundled MCP server requests these scopes:

```text
notes.read actions.read actions.write automation.read automation.write
```

If authentication does not start automatically, run this from a terminal:

```bash
codex mcp login memova --scopes notes.read,actions.read,actions.write,automation.read,automation.write
```

Follow the browser login/consent flow, then return to Codex.

## Use The Plugin

In Codex, type `@memova` and choose a starter prompt, or ask:

```text
@memova Run latest final note workflow.
```

You can also select one of the plugin starter prompts:

```text
Setup my Memova knowledge base.
Run latest final note workflow.
Review latest Memova note and prepare engineering tasks.
Continue pending Memova automation tasks.
```

The workflow reviews recent Memova final notes, organizes engineering actions, asks before approval-required work, executes safe tasks when the current workspace is appropriate, and writes progress/results back to Memova.

On the first non-setup Memova workflow, the plugin checks whether a Memova knowledge-base vault is
already present on the Mac. If not, it shows one setup reminder, records that reminder locally under
`~/.cache/memova-codex-plugin/`, and does not repeat it on later workflows. Users can still start
setup explicitly with `@memova Setup my Memova knowledge base.`

The plugin also checks for newer Memova plugin releases at most once per day. If a newer version is
available, it reminds the user to upgrade, then repeats that reminder at most once every 7 days for
the same latest version.

## Set Up A Memova Knowledge Base

The knowledge-base setup flow is designed for users who already completed the Memova iOS setup step and marked setup ready for Codex.

In Codex, run:

```text
@memova Setup my Memova knowledge base.
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
7. Validate the Memova input-root manifest and required metadata files.
8. Report success or failure back to Memova through MCP, including
   `memova_input_root_relative_path`.

For a new iCloud vault, the usual Mac target path is:

```text
~/Library/Mobile Documents/com~apple~CloudDocs/Memova Vault
```

If the user connects an old Obsidian or Markdown vault, Codex preserves the user's structure. It
lightly scans for the best raw-input folder and creates only a scoped Memova input root after user
approval, for example:

```text
~/Library/Mobile Documents/com~apple~CloudDocs/Existing Obsidian Vault/00_Inbox/Memova
```

After Codex creates the vault/input root, the iOS app should ask the user to select the same folder
through Files and verify the Memova input-root `_memova/manifest.json`. Do not rely on the Mac
absolute path inside iOS; the manifest identifies the binding.

## File Tree Created By Setup

The actual file-tree implementation lives in:

```text
plugins/memova/skills/memova-vault-setup/scripts/memova_vault_lib.py
```

For a new vault, Codex creates an empty Memova vault skeleton and the Memova input root:

```text
README.md
AGENTS.md
inbox/
inbox/memova/
inbox/memova/README.md
inbox/memova/AGENTS.md
inbox/memova/schemas/*.schema.md
inbox/memova/meetings/
inbox/memova/imports/
inbox/memova/attachments/
inbox/memova/_memova/manifest.json
inbox/memova/_memova/input_root.json
inbox/memova/_memova/sync_state.json
inbox/memova/_memova/source_index.json
sources/
wiki/
projects/
daily/
outputs/
archive/
_memova/manifest.json
_memova/vault_mapping.json
_memova/sync_state.json
```

For an existing vault, Codex creates only the approved Memova input root, usually something like:

```text
00_Inbox/Memova/
00_Inbox/Memova/README.md
00_Inbox/Memova/AGENTS.md
00_Inbox/Memova/schemas/*.schema.md
00_Inbox/Memova/meetings/
00_Inbox/Memova/imports/
00_Inbox/Memova/attachments/
00_Inbox/Memova/_memova/manifest.json
00_Inbox/Memova/_memova/input_root.json
00_Inbox/Memova/_memova/sync_state.json
00_Inbox/Memova/_memova/source_index.json
```

Memova V1 writes raw meeting packets only under the Memova input root. It does not classify
meetings into projects, update wiki pages, or reorganize an existing knowledge base.

## What The Workflow Does

When triggered, the bundled `memova-workflow` skill tells Codex to:

1. Read recent Memova meetings and final notes through MCP.
2. Identify engineering-relevant tasks.
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
- Open `/plugins` and confirm `Memova` is installed and enabled.
- Start a new thread after installation.

If Memova tools are unavailable:

- Re-run the MCP OAuth login command above.
- Confirm the Memova account has access to the expected notes and actions.
- Confirm the MCP endpoint is reachable from the machine running Codex.

## Development

Validate JSON files:

```bash
python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
python3 -m json.tool plugins/memova/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/memova/.mcp.json >/dev/null
```

Validate skill metadata and helper scripts:

```bash
ruby -e 'require "yaml"; YAML.load_file("plugins/memova/skills/memova-workflow/agents/openai.yaml"); YAML.load_file("plugins/memova/skills/memova-vault-setup/agents/openai.yaml"); puts "yaml ok"'
python3 -m py_compile plugins/memova/skills/memova-vault-setup/scripts/*.py
python3 plugins/memova/skills/memova-vault-setup/scripts/create_memova_vault.py discover
python3 plugins/memova/scripts/version_check.py --force
python3 plugins/memova/scripts/kb_setup_reminder.py
```

Inspect the marketplace locally:

```bash
codex plugin marketplace add .
```
