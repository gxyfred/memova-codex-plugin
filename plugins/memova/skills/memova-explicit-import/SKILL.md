---
name: memova-explicit-import
description: Preview, locally filter, and import only text the user explicitly selects in the current request, including an excerpt, an attached text resource, or a client-provided task/date-range export. Never enumerate or reconstruct general Codex history.
---

# Memova Explicit Import

Import only content affirmatively selected by the user in the current request. Default to the
smallest scope that satisfies the request.

## Allowed sources

- text pasted or quoted by the user;
- an exact excerpt already visible in the current conversation;
- an exact attached text resource named by the user;
- a task or date-range export explicitly supplied by the client/user for this import.

A task id or date range alone is not permission to enumerate Codex history. If the client has not
provided the selected content as current context or an attachment, ask the user to export/attach it.
Never call App Server `thread/list`/`thread/read`, parse Codex JSONL/SQLite, scan filesystem history,
or scrape UI as a fallback.

## Preview and local filtering

For an attached UTF-8 text file, run the deterministic helper only against the exact user-selected
path:

```bash
python3 plugins/memova/skills/memova-explicit-import/scripts/preview_selected_import.py \
  --input-file "<selected-file>" \
  --selection-kind "<excerpt|task|date_range|uploaded_resource>" \
  --source-label "<user-visible label>" \
  --source-reference "<opaque selected-source id>" \
  --output-file "<private temporary sanitized file>"
```

For short pasted/current-context text, provide it to the same helper on standard input with
`--stdin`; do not place content in shell arguments. The helper accepts at most 100,000 UTF-8 bytes,
replaces detected credentials with typed redaction markers, and returns hashes/counts without
printing secret values.

Before any MCP write, show an accurate preview containing:

- preview id/time, selection kind, user-visible source label, and opaque source reference;
- exact original and sanitized byte/character counts and SHA-256 hashes;
- restricted-data finding counts by type, never matched values;
- the complete sanitized text when reasonably bounded, otherwise a local preview/output path the
  user can inspect;
- the Memova account/workspace destination when available.

If the scanner cannot decode/inspect a resource, stop. Do not upload the raw file as a fallback.
Pattern filtering reduces risk but cannot guarantee that every secret was detected; say so.

## Import

Obtain explicit approval immediately after showing the sanitized preview. Then call the Memova MCP
tool `import_selected_codex_content` with exactly the approved sanitized text, selection metadata,
preview hashes, scan version, and `selected_import_confirmed=true`.

Do not modify the content after approval. Do not add repository names, paths, branches, other chat
messages, inferred profile data, or surrounding context. If the tool is unavailable, report that
the backend selected-import contract is not deployed; never fall back to background-history access.

The tool succeeds only after both the durable archive ACK and the deterministic Knowledge V5 Codex
Session commit succeed. Report `knowledge_v5_status=ready` only when the tool returns it. Here,
`ready` means the exact approved text is stored as the canonical V5 Codex Session without inferred
semantic links or model processing. Keyword/vector retrieval remains subject to the backend's V5
search rollout; `ready` does not mean Personal Manual or semantic enrichment has run. If the tool
reports that the archive is durable but the V5 commit failed, retry only the same approved preview
when `retry_same_preview=true`; never widen or reconstruct the source scope.

For deletion, show the exact returned `external_thread_id`, obtain adjacent explicit confirmation,
and call `delete_selected_codex_import` with a new stable request id and `delete_confirmed=true`.
This selected-import deletion tool must never be used for background-history archives.
