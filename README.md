# Memova Codex Plugin

Codex plugin marketplace for Memova.

This plugin bundles:

- the Memova OAuth MCP server at `https://api.memova.ai/mcp`,
- the `memova-workflow` skill for one-click final-note workflows,
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
Run latest final note workflow.
Review latest Memova note and prepare engineering tasks.
Continue pending Memova automation tasks.
```

The workflow reviews recent Memova final notes, organizes engineering actions, asks before approval-required work, executes safe tasks when the current workspace is appropriate, and writes progress/results back to Memova.

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

Inspect the marketplace locally:

```bash
codex plugin marketplace add .
```
