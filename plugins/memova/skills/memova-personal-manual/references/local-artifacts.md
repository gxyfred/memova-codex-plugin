# Personal Manual Plugin local artifact contract

The Memova MCP `get_personal_manual_generation_contract` result is authoritative for analysis,
scoring, writing, privacy, and upload behavior. This file defines only the Codex Plugin's local
audit artifacts.

Write `personal-manual-scores.csv` with exactly these columns:

```csv
category,key,value,confidence
```

Required rows:

- `archetype,work_archetype,<exact Work Archetype>,`
- `dimension,dimension_1,<0-100>,<0-1>` through `dimension_4`
- `overall,archetype_confidence,<1-100>,`

Add one `facet,<facet name>,<0-100>,<0-1>` row for each internally scored facet. Facet rows stay
local and must never enter the Manual, upload JSON, or MCP call.

Write `personal-manual-sources.csv` with exactly these columns and exactly two rows:

```csv
source_type,conversation_count,turn_count,status
codex,<exact count>,<exact count>,available
chatgpt,<exact count>,<exact count>,<available or unavailable>
```

Never fabricate availability or counts. Total inspected conversations must be between 1 and 50.
