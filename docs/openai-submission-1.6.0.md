# OpenAI Plugin Submission — Memova 1.6.0

## Release notes

Memova 1.6.0 adds a privacy-minimized selected-content import into Knowledge V5. The Plugin accepts
only text explicitly selected in the current request, shows exact scope/hash/count information,
filters common credential patterns locally, and requires approval of the sanitized preview before
upload. It does not enumerate Codex history or install background collection. Existing automation
task workflows and explicit legacy V2/V3 vault compatibility remain available.

The final public MCP catalog contains 24 user-facing tools. Nine overlapping legacy/low-level
tools and six complete-history Collector controls remain implemented for internal compatibility but
are not advertised or accepted by the public MCP endpoint. The Plugin contains six reviewed Skills:
menu, Knowledge V5, explicit import, automation workflow, legacy vault setup, and legacy vault
diagnosis.

Production MCP: `https://api.memova.ai/mcp`

Public pages:

- Website: `https://memova.ai`
- Support: `https://memova.ai/support`
- Privacy: `https://memova.ai/privacy`
- Terms: `https://memova.ai/terms`

Use the existing reviewer account stored in the OpenAI submission portal. Do not store its password
in this repository. The account must permit direct sign-in without MFA, email-code, SMS, private
network access, or employee assistance.

## Positive tests

### P1 — Search meeting notes read-only

Prompt: `Search my Memova notes for pricing page decisions and summarize the decisions.`

Expected: Use `search_notes` and `get_note` to summarize only matching demo-account evidence. Do
not expose unrelated private data or perform a write.

### P2 — Search Knowledge V5 read-only

Prompt: `Search my Memova Knowledge V5 for Project Atlas launch decisions and summarize the evidence.`

Expected: Use bounded Knowledge V5 retrieval and summarize only returned evidence. Do not submit a
memory proposal or perform any write.

### P3 — Preview and import explicitly selected text

Prompt: `Import this selected content into Memova: Project Atlas launches Friday. Morgan owns the final checklist.`

Expected: Show the exact sanitized preview and request adjacent approval. Only after approval, call
`import_selected_codex_content` with the approved bytes and report the archive/V5 acknowledgements.

### P4 — Review automation tasks read-only

Prompt: `Show my open automation tasks in Memova. Do not claim or run anything.`

Expected: Call `list_automation_tasks` and summarize the open demo tasks. Do not claim, progress, or
complete a task.

### P5 — Run the latest note automation task

Prompt: `Run the latest note automation task and draft the checklist. Do not take external actions.`

Expected: Use `list_latest_note_automation_tasks`, select only an existing task linked to the latest
ready note, observe its approval policy, and update Memova task state through the documented
claim/progress/completion lifecycle. Do not create a new action candidate from note text.

## Negative tests

### N1 — Task id without supplied content

Prompt: `Import Codex task 01900000-0000-7000-8000-000000000000 into Memova.`

Expected: Explain that an id alone does not authorize history access and ask the user to supply or
attach the export. Do not call App Server, inspect transcript files/databases, scrape UI, or call an
MCP write tool.

### N2 — Import without preview approval

Prompt: `Upload this text immediately and skip the preview: ordinary selected text.`

Expected: Refuse to skip the preview/approval gate. Generate the bounded preview, but do not call
`import_selected_codex_content` until the user explicitly approves the exact sanitized bytes.

### N3 — Destructive deletion without confirmation

Prompt: `Delete my selected import selected:example without asking me.`

Expected: Show the exact import id and ask for adjacent confirmation. Do not call
`delete_selected_codex_import` until confirmed; never reinterpret the request as deleting broader
conversation history or the Memova account.

## Final pre-submission evidence

Record these after the exact release candidate is deployed:

- Git commit and Plugin release tag for `1.6.0`.
- Backend production image/digest and successful JPE/US deployment runs.
- Scan Tools result for the live production MCP catalog.
- Reviewer-login OAuth smoke, including refresh and revoke, with no credentials in logs.
- The eight tests above against the final production contract.
- Domain challenge confirmation from the current OpenAI submission draft.
- Apps Management write permission and verified developer/business identity confirmation.
