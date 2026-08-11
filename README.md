# Aegis 1.0

**Sovereign JIT token supply chain** for AI coding agents.

Reduce · reuse · recycle tokens. Pack context safely. Route models. Shrink & store finals. Ledger everything.

Absolute Form: austere · aggressive on drift · protective reserve (≥80%).

## Install

```bash
cd ~/Projects/aegis
python3 -m pip install --user -e .
# optional AST harden for py/js/ts/tsx:
python3 -m pip install --user -e ".[treesitter]"
python3 -m aegis doctor
python3 -m aegis version
```

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
aegis budget | surplus | doctor | langs | version
aegis idea list | audit | invest
```

## Data plane (`~/.aegis/`)

| Path | Role |
|------|------|
| `ledger.jsonl` | All token economics |
| `packs/` | Content-addressed context packs |
| `outputs/out_*.json` | Unified slim finals index |
| `fund.json` / `ideas.jsonl` | Surplus → ROI backlog |
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

**1.0.0** — compound platform milestone.

See [docs/EVOLUTION.md](docs/EVOLUTION.md) · [docs/ABSOLUTE.md](docs/ABSOLUTE.md) · [docs/FIELD.md](docs/FIELD.md)
