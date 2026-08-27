---
name: aegis-pack-first
description: >
  Before reading or editing a code file in Cursor, check the Aegis pack gate.
  Use when about to Read, open, or edit source; when reuse, pack, or cursor_last
  is mentioned; when reserve is throttle.
---

# Pack-first

Do this before any `Read` of a code file:

```bash
python3 -m aegis cursor --gate PATH --mode implement
```

- exit 0 / `action=reuse`: files are unchanged. Do **not** Read. Use `~/.aegis/cursor_last_context.md`.
- exit 1 / `action=pack`: pack once (first time, or after an edit), then edit from the bento only.

```bash
python3 -m aegis cursor --task "<intent>" --mode implement PATH
```

If the composer block says `reuse=hit`, never re-read `packed_paths`.
Reserve throttle/hard_stop: explore/reuse only — no invest, no parallel agents.
