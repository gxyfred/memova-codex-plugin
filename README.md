# Memova Codex Plugin

Private Codex plugin marketplace for Memova.

This plugin bundles:

- the Memova OAuth MCP server at `https://api.memova.ai/mcp`,
- the `memova-workflow` skill for one-click final-note workflows,
- Memova starter prompts and plugin presentation metadata.

## Install

From Codex CLI, add this marketplace:

```bash
codex plugin marketplace add gxyfred/memova-codex-plugin
```

Then open Codex and install the plugin:

```text
/plugins
```

Choose the `Memova Codex Plugins` marketplace, install `Memova`, and start a new thread.

If Codex asks for MCP authentication, complete the Memova OAuth flow. The bundled MCP server requests these scopes:

```text
notes.read actions.read actions.write automation.read automation.write
```

If authentication does not start automatically, run:

```bash
codex mcp login memova --scopes notes.read,actions.read,actions.write,automation.read,automation.write
```

## Use

In Codex, type `@memova` and choose a starter prompt, or ask:

```text
@memova Run latest final note workflow.
```

The workflow reviews recent Memova final notes, organizes engineering actions, asks before approval-required work, executes safe tasks when the current workspace is appropriate, and writes progress/results back to Memova.

## What This Is

This repository is a Codex plugin marketplace. It does not run a backend service and does not replace the Memova MCP server. The backend MCP endpoint remains `https://api.memova.ai/mcp`.

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
