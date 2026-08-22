# Personal Manual generation prompt v1

Use the locally filtered conversation evidence supplied by the Skill to generate an English
Personal Manual. The Skill, not this prompt, owns source discovery, the 50-conversation bound,
pagination, filtering, source availability, and exact source counts.

The manual contains two analytical layers. For the first layer, use the specified Big Five facets
and adjacent constructs internally to ground the analysis, but never mention Big Five, personality
traits, facet names, or psychometric terminology in the user-facing Manual.

This is an evidence-informed estimate of context-dependent working tendencies, not a clinical
assessment or fixed description of personality.

## Evidence rules

- Use repeated, concrete behavior: how the user frames, revises, explores, decides, requests
  structure, responds to alternatives, and expresses preferences.
- Give explicit self-descriptions and repeated choices more weight than writing style.
- Do not infer a tendency merely from the absence of behavior.
- Distinguish preference from ability.
- Account for task context. Describe variation instead of forcing one conclusion.
- Do not infer from protected or sensitive attributes.
- Require at least two independent pieces of evidence before a directional judgment.
- When evidence is insufficient or contradictory, move the score toward 50 and lower confidence.
- Do not reveal hidden reasoning. Provide only concise evidence summaries.

## Internal facet estimation

Estimate each relevant facet on a 0–100 scale:

- 50 means insufficient evidence or balanced.
- Below 50 means relatively lower expression in this history.
- Above 50 means relatively higher expression in this history.

Assign each estimate an evidence confidence from 0 to 1. These values are not population
percentiles.

## Composite dimensions

Calculate each dimension as a confidence-weighted normalized mean. Reverse-code an indicator with
`100 - indicator_score` when it supports the left rather than right pole.

### Dimension 1: Think it through ↔ Talk it through

The right pole is supported by Gregariousness, Friendliness, Excitement-seeking, and evidence that
ideas are discovered, developed, or revised through active dialogue. Use Ideas only as contextual
evidence. Intellectual engagement affects this dimension only when the evidence shows whether it
happens primarily through private reflection or interactive exchange.

### Dimension 2: Find the path ↔ Map the path

The right pole is supported by Order, Deliberation, Self-discipline, reverse-coded
Adventurousness, and reverse-coded ambiguity acceptance. Interpret this specifically as whether
the user prefers to define structure before proceeding or discover structure through iteration.

### Dimension 3: Go deeper ↔ Go wider

The right pole is supported by Ideas, Imagination, Adventurousness, divergent thinking,
exploration, and breadth. The left pole is supported by convergent thinking, exploitation or
refinement of a promising direction, and sustained elaboration of an existing frame. Do not assume
that a lower right-pole score means low curiosity.

### Dimension 4: Understated ↔ Expressive

The right pole is supported by Assertiveness, Positive Emotionality, Aesthetics, Feelings, and
reverse-coded Modesty. Expression means the visibility, distinctiveness, emotional color, and
rhetorical force of communication, not the strength of underlying beliefs.

For each dimension:

1. Convert every indicator to the direction of the right pole.
2. Weight every indicator by evidence confidence.
3. Calculate `score = Σ(indicator_score × confidence) ÷ Σ(confidence)`.
4. Shrink sparse evidence toward 50.
5. Round to the nearest whole number.
6. Assign Low, Moderate, or High evidence confidence.

Interpret scores as follows: 0–20 strongly left; 21–40 moderately left; 41–59 balanced,
contextual, or uncertain; 60–79 moderately right; 80–100 strongly right.

## Work Archetype

Use the four dimensions to choose the nearest archetype. Archetype selection and the overall
confidence formula are content-owned; development only transports the results.

| # | Archetype | Clarity | Navigation | Scope | Expression |
|---:|---|---|---|---|---|
| 1 | The Refiner | Private | Find | Deep | Understated |
| 2 | The Maker | Private | Find | Deep | Expressive |
| 3 | The Scout | Private | Find | Wide | Understated |
| 4 | The Pathfinder | Private | Find | Wide | Expressive |
| 5 | The Builder | Private | Map | Deep | Understated |
| 6 | The Curator | Private | Map | Deep | Expressive |
| 7 | The Cartographer | Private | Map | Wide | Understated |
| 8 | The Visionary | Private | Map | Wide | Expressive |
| 9 | The Listener | Dialogic | Find | Deep | Understated |
| 10 | The Improviser | Dialogic | Find | Deep | Expressive |
| 11 | The Forager | Dialogic | Find | Wide | Understated |
| 12 | The Explorer | Dialogic | Find | Wide | Expressive |
| 13 | The Examiner | Dialogic | Map | Deep | Understated |
| 14 | The Guide | Dialogic | Map | Deep | Expressive |
| 15 | The Gatherer | Dialogic | Map | Wide | Understated |
| 16 | The Conductor | Dialogic | Map | Wide | Expressive |

## Context-independent synthesis

Before writing, silently analyze recurring patterns across different topics and periods. Treat AI
interaction as one observation context, not as the user's personality. Downweight behaviors likely
caused by the medium itself, including prompting conventions, revisions, managing agents,
debugging, asking for sources, and specifying output formats.

Prioritize patterns likely to remain relevant in everyday life, relationships, decisions, and
non-AI collaboration:

- how ambiguous situations and tradeoffs are framed;
- what the user consistently notices, protects, or resists;
- responses to uncertainty, disagreement, responsibility, mistakes, and incomplete control;
- balances among autonomy, trust, quality, speed, expression, and human consequences;
- recurring differences between stated aims and observed behavior.

Require repeated evidence across contexts. Omit weak claims instead of filling sections with
generic inference. If a statement could describe most thoughtful, capable AI users, make it more
specific or remove it. Look for distinctive combinations, boundary conditions, and less obvious
values beneath repeated behavior. Include at least one well-supported observation the user may not
readily recognize, but do not force surprise.

Do not mention specific conversations, projects, tools, roles, or personal events. Translate the
evidence into context-independent real-life language. Write naturally in the first person without
psychological or corporate jargon.

## `personal-manual.md` contract

Write exactly these headings in this order. Do not add headings. Keep `Work Archetype:` on one
line. For list sections, use Markdown `- ` bullets. The two keyword lines under People and
Environments may contain up to five comma-separated keywords; they remain content-audit text and
the backend currently uses its archetype catalog for displayed keywords.

```text
Work Archetype: [The Conductor/The Gatherer/...]
1. How I Operate
How I think
[35–50 words describing how I understand complexity, form judgments, and decide.]
How I read
[30–40 words describing what helps me understand writing and what loses attention.]
How I write
[30–40 words describing how I develop/refine ideas and authentic expression.]
2. What Moves and Grounds Me
What gives me energy
- [Up to three concise bullets.]
What I care about
- [Up to three concise bullets; at least one should reveal a non-obvious demonstrated value.]
3. Relationships and Collaboration
How I communicate
[35–50 words covering needs, context, questions, disagreement, listening, and understanding.]
How to work with me
- [Up to three observable recommendations covering decisions, feedback, disagreement, autonomy, and follow-through.]
People that help me thrive
[Up to five comma-separated keywords]
[35–45 word explanation of complementary interpersonal qualities.]
Environments that help me thrive
[Up to five comma-separated keywords]
[40–50 word explanation of conditions for engagement, development, and sustainable progress.]
4. What Makes Me Distinctive
My strengths
[40–55 words describing the most transferable, unusual combination of abilities.]
Current growth edge
[40–55 words identifying one actionable capacity, the strength beneath it, and observable growth.]
Internal conflicts
- [Up to three concise bullets describing genuinely recurring qualities pulling in different directions.]
5. Moving Forward
The person I am trying to become
[45–60 words describing two or three capacities that preserve what works while improving effectiveness, intention, or fulfillment.]
Advice from Memova
- [Two or three practices, each no more than 25 words. No pronouns. Each specifies an observable behavior and what to record in Memova, supporting practice → captured context → pattern recognition → better guidance.]
These results describe patterns visible in your available AI conversations. They may change across roles, tasks, and periods of life, and you can correct any interpretation that does not fit.
```

## Local CSV contracts

Write `personal-manual-scores.csv` with exactly these columns:

```csv
category,key,value,confidence
```

Required rows:

- `archetype,work_archetype,<exact Work Archetype>,`
- `dimension,dimension_1,<0-100>,<0-1>`
- `dimension,dimension_2,<0-100>,<0-1>`
- `dimension,dimension_3,<0-100>,<0-1>`
- `dimension,dimension_4,<0-100>,<0-1>`
- `overall,archetype_confidence,<1-100>,`

Add one `facet,<facet name>,<0-100>,<0-1>` row for every internally scored facet. Facet rows stay
local and must never be copied into the Manual, upload JSON, or MCP call.

Write `personal-manual-sources.csv` with exactly these columns and exactly two rows:

```csv
source_type,conversation_count,turn_count,status
codex,<exact count>,<exact count>,available
chatgpt,<exact count>,<exact count>,<available or unavailable>
```

Never fabricate source availability or counts. Total inspected conversations must be between 1 and
50.

## Final writing rules

- Keep the complete Manual concise, memorable, and easy to share.
- Prefer specific behavioral language over labels, praise, and clichés.
- Make every section contribute new information; avoid repetition across headings.
- Preserve nuance through precise wording rather than extra length.
- Avoid diagnostic language and false certainty.
- Do not mention AI, ChatGPT, Codex, prompts, or agents inside the Manual body, except the required
  final disclaimer.
- Do not describe ordinary knowledge-work behavior as a distinctive personality characteristic.
- Qualify or omit context-bound and uncertain claims.
- Optimize for recognition: the person should feel accurately seen in useful, non-obvious ways.
