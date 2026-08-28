# Personal Manual Plugin local artifact contract

The Memova MCP `get_personal_manual_generation_contract` result is authoritative for analysis,
scoring, writing, privacy, and upload behavior. This file defines the Codex Plugin's temporary
audit CSV format. The exact UTF-8 CSV text is uploaded as private version metadata and then the
temporary files are deleted; conversation content is never uploaded.

Write `personal-manual-scores.csv` with exactly these columns:

```csv
category,key,value,confidence
```

Required rows:

- `archetype,work_archetype,<exact Work Archetype>,`
- `dimension,dimension_1,<0-100>,<0-1>` through `dimension_4`
- `overall,archetype_confidence,<1-100>,`

Add one `facet,<facet name>,<0-100>,<0-1>` row for each internally scored facet. Use only facet names
listed in the canonical generation contract. Facet rows must never enter the Manual or public
document; they travel only inside the validated private scores CSV string.

Write `personal-manual-sources.csv` with exactly these columns and one row per aggregate evidence
source:

```csv
source_name,source_kind,item_count,visible_text_unit_count,status
Codex,conversation_history,<exact task count>,<exact visible message count>,available
```

Use `source_kind=conversation_history` only for the invoking Codex agent's native task history. Add
an `explicit_user_content` row only when the user actually included or selected content for this
run. Never add ChatGPT chats, Memova notes, meeting content, source ids, or evidence text. Source
names must be distinct visible labels of at most 64 characters. There may be at most eight rows;
total inspected available items must be between 1 and 20. An unavailable row must have zero counts,
and every positive item count must have a positive visible-text-unit count. Never fabricate
availability or counts. The rows must exactly match the upload payload's `evidence_sources`.
