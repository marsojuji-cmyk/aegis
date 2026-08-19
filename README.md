# Aegis 1.2.0

**Agent operating system** for AI coding work: kernel (process / memory / drivers / syscalls), portable data plane, frozen `/v1` API, honest yield proof.

Reduce · reuse · recycle tokens. Pack context. Gate tools. Land receipts. Ledger everything.

Absolute Form: austere · aggressive on drift · protective reserve (≥80%).

## Install (any machine)

```bash
python3 -m pip install --user -e .
python3 -m aegis os init
python3 -m aegis doctor --product
python3 -m aegis os ready
python3 -m aegis os score
```

Optional: `pip install --user -e ".[treesitter]"`. Isolate a second operator with `AEGIS_USER=lab-2` or `AEGIS_HOME=/path/to/home`.

This-host extras (Cursor/Hermes/AGIS) remain optional. They are not required for `doctor --product`.

## Core loop

```text
pack once → reuse while bytes unchanged → land → ledger
```

Covering reuse: a later pack of a **subset** of those files hits if the hashes still match. After you edit, the cache misses on purpose.

## Commands (high yield)

```bash
# Pack / reuse
aegis pack --mode implement path.py
aegis cursor --gate path.py
aegis cursor --task "…" --mode implement path.py

# Release gate
aegis os ready
aegis price quote
aegis demo start
aegis demo run src/aegis/pricing.py
aegis demo status
aegis doctor --product
aegis decisions health
aegis modules health
aegis yield report

# Land
aegis land --body-file final.txt --summary "what shipped"

# Ops
aegis os init|score|backup|restore|uninstall|bench|ready
aegis budget | surplus | version
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
- Pack cache: covering path-set + file hashes (task does not bust reuse; **edits do**)  
- Concurrent batch default: **16** (cap 32) — frozen under throttle  
- Pack reuse aim: **≥50%** hit rate (BUILD until met). Same files, unchanged bytes.

## Version

**1.2.0** — Master Aegis product OS (`pyproject.toml` / `src/aegis/__init__.py`). Hermes plugin identity stays 1.0.0. `savings_percent` remains null without an admitted pair.

See [docs/EVOLUTION.md](docs/EVOLUTION.md) · [docs/ABSOLUTE.md](docs/ABSOLUTE.md) · [docs/FIELD.md](docs/FIELD.md)
