---
name: aegis-continuity
description: >
  Start and checkpoint Aegis continuity for long or multi-file Cursor tasks.
  Use when implementing across files, transferring a chat, or compacting context.
---

# Continuity

Long or multi-file work:

```bash
python3 -m aegis continuity start --task "<intent>" --mode implement path [path...]
```

Use the printed bento. Do not re-read packed trees. Capsule `artifacts` include `pack_id`.

At checkpoint or handoff:

```bash
python3 -m aegis continuity checkpoint --objective "..." --verified "..." --next-action "..."
```

Empty pack (no existing files or neighbors) is a hard fail — pass a real path.
Start the next task from the capsule, not chat history.
