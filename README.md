# Aegis 1.2.0

**Agent operating system** for AI coding work: kernel (process / memory / drivers / syscalls), portable data plane, frozen `/v1` API, honest yield proof.

Reduce · reuse · recycle tokens. Pack context. Gate tools. Land receipts. Ledger everything.

Absolute Form: austere · aggressive on drift · protective reserve (≥80%).

## Install (any machine)

```bash
python3 -m pip install --user -e .
python3 -m aegis os init
python3 -m aegis doctor --product
python3 -m aegis os score
```

Optional: `pip install --user -e ".[treesitter]"`. Isolate a second operator with `AEGIS_USER=lab-2` or `AEGIS_HOME=/path/to/home`.

This-host extras (Cursor/Hermes/AGIS) remain optional. They are not required for `doctor --product`.

## Core loop

```text
preflight → pack (quality) → receipt → output lane
  → model/router → shrink/store/reuse → ledger → surplus/ideas
```

## Commands (high yield)

```bash
# Pack / preflight
aegis pack --task "…" --mode explore|implement path.py
aegis preflight --task "…" --mode implement path.py

# Cursor Composer
aegis cursor --install
aegis cursor --task "…" --mode implement path.py
aegis cursor --gate path.py
aegis cursor --outputs

# Universal router (10×)
aegis run --model mock|ollama|grok|claude|openai|antigravity --task "…" [files]
aegis run --batch jobs.json --workers 16
aegis serve --background --port 8787   # background router
aegis daemon start|stop|status|restart
aegis daemon install-login             # start at login (launchd)
aegis daemon uninstall-login
aegis app build|open                   # SwiftUI menu bar (ledger + daemon)
aegis intel status|tick|forecast|usage|report   # Intelligence Layer (autonomous compound)
aegis providers

# Wrappers (OpenAI / Anti-Gravity intercept)
aegis wrap --provider openai --task "…" --prompt "…" [files]
aegis wrap --provider antigravity --task "…" --prompt "…" --dry-run
# Python: from aegis.wrappers import OpenAIWrapper, AntiGravityWrapper

# Output reduce (thought→ship)
aegis land --body-file final.txt --summary "what shipped"
aegis output-get out_<id>

# Ops
aegis os init|score|backup|restore|uninstall|bench
aegis kernel status|ps|mem|drivers|pack
aegis api spec|check
aegis yield prove path.py | yield report
aegis budget | surplus | doctor --product | langs | version
aegis idea list | audit | invest
aegis sprint seed | list | report | board
aegis hermes search "query" | hermes resolve "note"
```

## Data plane (`~/.aegis/`)

| Path | Role |
|------|------|
| `ledger.jsonl` | All token economics |
| `packs/` | Content-addressed context packs |
| `outputs/out_*.json` | Unified slim finals index |
| `fund.json` / `ideas.jsonl` | Surplus → ROI backlog |
| `sprints.jsonl` | Sprint ledger (`aegis sprint`) |
| `MANIFEST.json` | Schema 2 portable home marker |
| `kernel/` | Process table + syscall stats |
| `backups/` | `aegis os backup` archives |
| `config.toml` | Cap, reserve floor, reinvest rate |

## Compound engine (languages)

| Tier | Languages |
|------|-----------|
| First-class + tree-sitter | Python, JS, TS, TSX (validated) |
| Structured | Java, Kotlin, C#, Go, Rust |
| Scrub-only | Everything else (implement = full file) |

## Policy defaults

- Weekly cap: 1_000_000 processed tokens  
- Reserve floor: 80% (invest freezes below)  
- Reinvest: 20% of new savings → wish jar  
- Pack cache: mode map + path-set (task does not bust reuse)  
- Concurrent batch default: **16** (cap 32)  
- Output reuse aim: **≥50%** pack hit rate (BUILD until met)

## Version

**1.2.0** — Master Aegis product OS (`pyproject.toml` / `src/aegis/__init__.py`). Hermes plugin identity stays 1.0.0. `savings_percent` remains null without an admitted pair.

See [docs/EVOLUTION.md](docs/EVOLUTION.md) · [docs/ABSOLUTE.md](docs/ABSOLUTE.md) · [docs/FIELD.md](docs/FIELD.md)
