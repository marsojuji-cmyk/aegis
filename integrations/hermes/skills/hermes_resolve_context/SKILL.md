---
name: hermes_resolve_context
description: Bounded graph context from a note id or title. JSON only. Read-only.
---

# hermes_resolve_context

Use for a one-seed graph walk. Not lexical search (`hermes_notes_search`).

```
{"note_id": "Memory Utility Labs.md", "project": "aegis", "depth": 1, "max_notes": 8}
{"title": "Memory Utility Labs", "depth": 1}
```

Aliases: `title` / `query` → `note_id`; `max_hops` → `depth`; `max_chars` → `max_body_chars`. Unresolved wikilinks stay unresolved. Default 8 notes / 4000 chars may truncate. Do not write to Hermes memory.
