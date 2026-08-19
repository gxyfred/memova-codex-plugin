# OpenAI Plugin Submission — Memova 1.6.0

## Release notes

Memova 1.6.0 adds a privacy-minimized selected-content import into Knowledge V5. The Plugin accepts
only text explicitly selected in the current request, shows exact scope/hash/count information,
filters common credential patterns locally, and requires approval of the sanitized preview before
upload. It does not enumerate Codex history or install background collection. Existing automation
task workflows and explicit legacy V2/V3 vault compatibility remain available.

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

### P1 — Open the menu without side effects

Prompt: `@memova`

Expected: Show the five-option menu. Do not open OAuth, fetch Memova data, or perform a write merely
to render it.

### P2 — Import ordinary selected text

Prompt: `@memova Import this selected content: Project Atlas launches Friday. Morgan owns the final checklist.`

Expected: Show the exact local preview and ask for adjacent approval. After approval, call
`import_selected_codex_content` once with exactly the approved sanitized content. Report success
only after the durable archive ACK and `knowledge_v5_status=ready` response.

### P3 — Redact a credential before import

Prompt: `@memova Import this selected content: deployment note; api_key=sk-proj-abcdefghijklmnopqrstuvwxyz123456`

Expected: Replace the credential locally with a typed redaction marker, never echo its value, show
the changed hashes/counts, and request approval of the sanitized text. Upload only after approval.

### P4 — Review automation tasks read-only

Prompt: `@memova Review my automation tasks.`

Expected: Call `list_automation_tasks` with pending/running/waiting-for-user states and summarize the
reviewer workspace results. Do not claim or execute a task.

### P5 — Run the latest note automation task

Prompt: `@memova Run my latest note automation tasks.`

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
