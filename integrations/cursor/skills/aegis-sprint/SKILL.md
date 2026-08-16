---
name: aegis-sprint
description: >
  Track Aegis work in sprints. Use when asked for status, board, plan, close a
  sprint, or what is parked. Do not re-read the full D/R/Q registers first.
---

# Sprint

```bash
python3 -m aegis sprint report
python3 -m aegis sprint list
python3 -m aegis sprint start SP-NNN
python3 -m aegis sprint complete SP-NNN --verified "..." --evidence "..."
```

Ledger: `~/.aegis/sprints.jsonl`. Board: `05_SPRINT_BOARD.md`.
Registers remain SoT for D/R/Q. Parked/blocked sprints refuse start unless unparked.

Do not invent a second tracker (Linear/Notion) for Aegis iteration.
