# Evolution doctrine

1. **Continuity** — old name/paths still work  
2. **Justification** — each epoch fixes pain the prior measured  
3. **Yield** — same-day CLI/test  

## Spine

```text
E0 compat → E1+ piggy bank + 3R + surplus→ideas
  → E2 safe pack modes → … → feedback
```

## E1+ closed loop

```text
pack/scrub/output → REDUCE
                 → REUSE (pack cache)
                 → ledger (piggy bank)
                 → reserve OK?
                      no  → freeze invest
                      yes → surplus credits → idea backlog → improve Aegis
```

## Done (E1+)

- [x] Durable `~/.aegis/ledger.jsonl`
- [x] Pack cache reuse hits
- [x] Output profiles + record-out
- [x] Surplus fund + ideas + invest gate

## Done (E2)

- [x] Product pack engine (`bento` + `ast_slice`)
- [x] implement: full target bodies + neighbor sigs
- [x] explore: imports + signatures only
- [x] Fidelity tests; `--target` / `--legacy` flags

## Done (post-E2 compound)

- [x] Reuse hit-rate dashboard in `budget` / `surplus` / report JSON
- [x] Low-reuse cue when attempts ≥ 3 and rate &lt; 20%
- [x] Skill Absolute Form + output profiles wired
- [x] `aegis receipt` + `~/.aegis/last_pack.json` for agent turns
- [x] Backlog closed: hit-rate, skill wire, pack receipt (4 winners, 0 misses)

## Done (E3)

- [x] Multi-lang scrub (`scrub.py`) by detected language
- [x] TS/JS structure slice (explore/implement/review) without tree-sitter
- [x] Scrub-only + full-file implement for unknown langs (Go, etc.)
- [x] `slice_router` + engine `product_e3`
- [x] Go structure slicer (func/method/type)
- [x] Rust structure slicer (fn/struct/enum/impl/trait)
- [x] Pack quality gates (`quality.py`, `--strict`)
- [x] Auto-receipt on every pack (opt-out `--no-receipt`)
- [ ] tree-sitter — parked (D, only if TS/JS fails in wild)
- [x] Java/C# structure slicer (class/method/interface/namespace) v0.7.1
- [x] Reuse boost: cache key = mode + path hashes + targets (task optional) v0.8.0
- [x] Pack token honesty: code-only counts (strip annotation chrome) v0.8.0
- [x] Agent preflight (`aegis preflight`) + auto-recover explore v0.9.0
- [x] Output lane activation (`output_lane`, budget out meters) v0.9.0
- [x] Kotlin slicer + py/java/kotlin first-class engine v0.10.0
- [x] Reuse mode-map + path-set fingerprint + review→explore fallback v0.10.0
- [x] Output land (`aegis land`) closes actual-out loop v0.10.0
- [x] Tree-sitter optional backend for Python/JS/TS (fallback regex/stdlib) v0.11.0
- [x] TSX grammar (language_tsx) with React fixture validation + TS/regex fallback v0.11.1
- [x] Output reduce path: shrink+store+reuse finals (`output_store`, `aegis land --body`) v0.12.0
- [x] Universal router: providers + daemon + `aegis run` concurrent batch v0.13.0
- [x] Cursor bridge: `.cursorrules` + `aegis cursor --task` composer route v0.13.1
- [x] **v1.0.0** — harden core · expand compound matrix · scale router (16 workers) · ship milestone
- [x] **v1.0.1** — OpenAI + Anti-Gravity wrappers (intercept → full pipeline)
- [x] **v1.0.2** — background daemon (`serve --background` / `daemon start|stop`)
- [x] **v1.0.3** — launchd login agent (`daemon install-login`) KeepAlive @ login
- [x] **v1.0.4** — SwiftUI menu bar app + `/v1/aegis/budget|ledger` for native UI
- [x] **v1.1.0** — Intelligence Layer: infinite compound loop, forecast, memory, auto-invest, cache optimizer
- [x] **v1.1.1** — Harden intel (policy_nudges, atomic IO, idempotent ticks, epoch 1.1) production-ready
- [x] **v1.1.1+** — Progressive burn (80/100/125), `/v1/aegis/burn`, events log, budget-aware workers, load-test
- [x] **Budget-Aware Mode** — hysteresis SM, module ranking/shed, tick gates, multi-surface fan-out
- [x] **Continuity Bridge** — emergency handoff report + embedding pack + Cross-AI next steps
- [x] **v1.2.0** — Master Aegis product OS: kernel, portable home, frozen `/v1`, yield harness
