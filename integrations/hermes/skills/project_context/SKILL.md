---
name: project_context
description: >
  Load session-scoped project context from PROJECT.md (goals, constraints, decisions).
  Use when Hermes needs current project goals or constraints.
---

# project_context

Session-scoped. Not Hermes memory. Empty workspace → no project until notes exist.

```bash
python3 scripts/hermes_org_skills.py note_graph --action rebuild --root "$AEGIS_HERMES_NOTES_ROOT"
python3 scripts/hermes_org_skills.py project_context --name aegis
```

Manifest sections: Goals, Constraints, Decisions. Frontmatter `project:` binds notes.
Do not call `memory.write` for this payload unless the user explicitly asks.
