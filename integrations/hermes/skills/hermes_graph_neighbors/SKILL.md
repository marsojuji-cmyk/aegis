---
name: hermes_graph_neighbors
description: Inbound/outbound wikilink neighbors for a note id or title.
---

# hermes_graph_neighbors

Use for a link list. No bodies. Prefer `hermes_resolve_context` when you need bounded neighbor text.

```
{"note_id": "Memory Utility Labs.md", "direction": "both", "hops": 1, "limit": 20}
{"title": "Memory Utility Labs", "direction": "outbound", "depth": 1}
```

direction: inbound | outbound | both. Aliases: `title` / `query` → `note_id`; `depth` → `hops`. Bounded. Not complete when truncated.
