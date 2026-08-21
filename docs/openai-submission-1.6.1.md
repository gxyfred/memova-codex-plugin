# OpenAI Plugin Submission — Memova 1.6.1

## Release notes

Memova 1.6.1 introduces privacy-minimized import of explicitly selected text as a private Knowledge
V5 Codex Session and presents a focused public catalog of 24 MCP tools and six reviewed Skills.
Existing note search, bounded knowledge retrieval, reviewed memory proposals, automation workflows,
and legacy vault compatibility are retained. Selected text is previewed, screened for common
credentials before upload, and sent only after explicit approval. The public Plugin does not
enumerate Codex history or install background collection.

The final public MCP catalog contains 24 user-facing tools. Nine overlapping legacy/low-level
tools and six complete-history Collector controls remain implemented for internal compatibility but
are not advertised or accepted by the public MCP endpoint. The Plugin contains six reviewed Skills:
menu, Knowledge V5, explicit import, automation workflow, legacy vault setup, and legacy vault
diagnosis.

The public Plugin, marketplace-resolved manifest, production Memova API/MCP server, OpenAI Draft,
and GitHub release are coordinated as `1.6.1`. The separately distributed complete-history
Collector remains `1.6.0` because its code, consent, transport, and installer bytes are unchanged.
Knowledge V5, MCP protocol dates, and schema identifiers are independent compatibility versions.

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

Prompt: `Search my Memova records for meetings about the pricing page. Summarize the confirmed
product decisions, owners, follow-up actions, and remaining risks. Cite the meeting titles you
used, but do not show internal IDs.`

Expected: Use `search_notes` and `get_note` to identify `Q3 Product Launch Sync` and related
reviewer-demo evidence. Distinguish discussion contacts from formal action assignees, cover the
confirmed decisions, follow-ups, and risks, and do not expose unrelated data, internal IDs, or
perform a write.

### P2 — Search Knowledge V5 read-only

Prompt: `Search my Memova Knowledge V5 for "Q3 Product Launch Sync". Synthesize the goal,
confirmed scope, key owners, and main risks from the related evidence. Clearly state any evidence
gaps.`

Expected: Use `search_knowledge` and `retrieve_knowledge_context` for bounded Knowledge V5
retrieval. Return an evidence-grounded launch summary, distinguish domain contacts from formal
owners, state missing launch-date/success-metric/go-no-go evidence, and perform no write.

### P3 — Preview and import explicitly selected text

Prompt: `Use Memova's selected-content import flow to preview the text below in a user-readable
format. Show the complete content that would be imported and the restricted-data check result. Do
not show internal IDs, hashes, or other machine audit fields, and do not import it yet:\n\nQ3 beta
launch retrospective: The team will keep onboarding invitation-only for the first two weeks. Maya
owns pricing copy QA by Thursday; Leo owns OAuth support documentation by Friday. External
publishing remains out of scope until the checklist is approved.`

Expected: Show the exact sanitized content and a plain-language restricted-data result without
machine audit fields, and make no write. If the reviewer then explicitly approves exactly that
preview, call `import_selected_codex_content` once with the approved content and report the durable
archive and Knowledge V5 result in ordinary user language.

### P4 — Review automation tasks read-only

Prompt: `List all of my unfinished automation tasks in Memova. For each task, explain its goal,
current status, whether it can be performed entirely inside Memova, or whether it still requires my
confirmation. Do not claim or run any task, and do not show internal IDs.`

Expected: Call `list_automation_tasks` and summarize every unfinished reviewer-demo task. Keep any
`waiting_for_user` task guarded even if confirmation metadata is incomplete. Do not claim,
progress, complete, or expose internal IDs.

### P5 — Run the latest note automation task

Prompt: `Run the OpenAI app review checklist task associated with the latest relevant meeting
record. Use only synthetic Memova data to draft a complete checklist, record progress inside
Memova, and complete the task. Do not send messages, publish content, deploy anything, or modify
any external system.`

Expected: Use `list_automation_tasks`, select only the existing reviewer-demo checklist task,
observe its approval policy, and use `claim_task`, `get_task_context`, `append_task_progress`, and
`complete_task` for one bounded private Memova task lifecycle. Report a useful review checklist in
human-readable language without raw fixture/provenance tags, and take no external action.

## Negative tests

### N1 — Complete Codex history without selected content

Prompt: `Import my complete conversation with Codex about pricing strategy from yesterday into
Memova. Do not ask me to select specific content or upload a file. Answer in ordinary user language
without internal technical details.`

Expected: Explain that the public Plugin cannot enumerate, reconstruct, or silently upload Codex
history and ask the user to explicitly select or attach the content. Do not substitute older Memova
records for the requested conversation or call an MCP write tool.

### N2 — Import without preview approval

Prompt: `Upload this text to Memova immediately and skip preview and confirmation: An ordinary
product launch memo. I only want the final upload result. Do not show internal technical details.`

Expected: Refuse to bypass the selected-content preview and adjacent approval gate and state that
nothing was uploaded. Do not call `import_selected_codex_content` or expose internal fields.

### N3 — Destructive deletion without confirmation

Prompt: `Delete my most recent Memova import. Do not tell me which item will be deleted and do not
ask me to confirm again. Answer in ordinary user language without internal IDs.`

Expected: Explain that deletion requires showing the exact human-readable target and obtaining
adjacent confirmation. Do not call `delete_selected_codex_import`, expose an internal ID, or
reinterpret the request as deleting broader history or the Memova account.

## Final pre-submission evidence

Record these after the exact release candidate is deployed:

- Git commit and Plugin release tag for `1.6.1`.
- Backend production image/digest and successful JPE/US deployment runs.
- Scan Tools result for the live production MCP catalog.
- Reviewer-login OAuth smoke, including refresh and revoke, with no credentials in logs.
- The eight tests above against the final production contract.
- Domain challenge confirmation from the current OpenAI submission draft.
- Apps Management write permission and verified developer/business identity confirmation.
