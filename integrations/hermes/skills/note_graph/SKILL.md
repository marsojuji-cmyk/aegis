---
name: note_graph
description: >
  Index local Markdown notes and query [[wikilinks]], tags, and orphans.
  Use when Hermes needs note links, tagged notes, or orphan notes.
---

# note_graph

Local index only. Rebuild allows the pinned `hermes_notes_root` / `AEGIS_HERMES_NOTES_ROOT`, or the FIRST_RELEASE AGIS corpus when unset. Documents Labs and `/Users/ektar/workspace` are rejected.

```bash
python3 scripts/hermes_org_skills.py note_graph --action rebuild --root "$AEGIS_HERMES_NOTES_ROOT"
python3 scripts/hermes_org_skills.py note_graph --action linked_to --target "Aegis Gate"
python3 scripts/hermes_org_skills.py note_graph --action tagged --tag hermes
python3 scripts/hermes_org_skills.py note_graph --action orphans
```

Reads go through AEGIS `read_file`. Writes land in `~/.aegis/hermes_index/{notes,graph,projects}.json`.
Do not write results to Hermes `memory` unless the user asks.
