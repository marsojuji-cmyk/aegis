---
name: aegis-hermes
description: >
  Read-only Hermes note/file/project search and bounded context resolve.
  Use when asking what we decided, vault notes, MUL corpus, or graph neighbors.
---

# Hermes retrieval

```bash
python3 -m aegis hermes search "query" [--kind note|file|project] [--tag TAG]
python3 -m aegis hermes resolve "note or query" [--project NAME]
```

Local indexes only (`~/.aegis/hermes_index`). No external search API.
Empty hits are success. Do not write Hermes memory. Do not walk the vault by hand.
Canonical notes root is AGIS `AEGIS/05-Memory-Utility-Labs`, not Documents Labs.
