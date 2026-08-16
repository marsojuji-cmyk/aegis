---
name: hermes_project_context
description: Bounded project context JSON plus a text packet with provenance.
---

# hermes_project_context

Use for a project-scoped packet. For one note plus neighbors, use `hermes_resolve_context`.

```
{"project": "aegis", "query": "gate", "max_notes": 8, "max_total_chars": 4000}
```

Session-scoped. `persisted_to_memory=false`. Truncation sets truncated=true and a warning.
