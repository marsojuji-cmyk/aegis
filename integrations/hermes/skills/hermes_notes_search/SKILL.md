---
name: hermes_notes_search
description: Lexical search of the local note graph by query, project, and tags. JSON only.
---

# hermes_notes_search

Use to find notes by text. Not a graph walk (`hermes_resolve_context`).

```
{"query": "guard_shadow_mode", "project": "aegis", "limit": 10}
```

Empty hits are success. Empty query is INVALID_ARGUMENT. `root` overrides are rejected. Requires a prior in-memory graph. Do not write to Hermes memory.
