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

Write `personal-manual-sources.csv` with exactly these columns and exactly two rows:

```csv
source_type,conversation_count,turn_count,status
codex,<exact count>,<exact count>,available
chatgpt,<exact count>,<exact count>,<available or unavailable>
```

Never fabricate availability or counts. Total inspected conversations must be between 1 and 50.
