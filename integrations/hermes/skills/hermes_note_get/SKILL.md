---
name: hermes_note_get
description: Fetch one note by id or title. Rejects path traversal.
---

# hermes_note_get

Use after search when you need one note. Not a graph walk.

```
{"note_id": "Memory Utility Labs.md", "include_body": true}
{"title": "Memory Utility Labs", "include_body": true}
```

Aliases: `title` / `query` → `note_id`. Duplicate titles return AMBIGUOUS_TITLE. `..` returns PATH_NOT_ALLOWED.
