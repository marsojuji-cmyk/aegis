# Aegis Project Memory

## Architecture
- 1.2.0 agent OS: kernel + portable schema-2 home + frozen `/v1` + yield on 1.1.1 JIT chain.
- Hermes: normalize → policy → redact → allow|deny|require-review → `~/.aegis/guard_log.jsonl`.
- `savings_percent` null unless admitted pair. Sprints: `aegis sprint`. Pack-first; `reuse=hit` → no packed_path re-read.

## Standing decisions
- D-011: shadow on. Q-011 open (blocked). D-013/D-017: live `aegis-gate`.
- D-015/D-016: no pair/`token_delta` until admission + named model.
- D-018/D-021: daemon bind/health; bindError preserved; failed start reaps.
- D-019: R-012 at gate only. R-014/Q-012 parked. D-020: memory is write. R-015 open.
- D-022–D-024: file index, note graph, local search. D-025 sprint CLI. D-026 pack_id + empty-pack refuse.
- D-027 skills via `aegis cursor --install`. D-029 Flow. D-030 MUL graph 9→20; D-033/D-034 named 20→32 research-log+provenance set; unbounded growth frozen.
- D-031: 1.2.0 OS. Overlay ≠ SKU. `doctor --product` is second-machine floor.
- D-032: covering reuse + hash verify. `os ready`. Freeze+honest yield on doctor.
- M-001..M-014: budget modules. Ghost enrichment removed. `opt_in` fail-closed.
- Price: replacement-cost quote. Exclusive mid ~$107k. Hosted not a SKU. `aegis price`.
- Next 30d (W34 throttle 75.68%): Path A close source $45k if a named buyer in 14d; else Path B reuse-only to 50%. No new modules / hosted / pair-as-marketing.
- Last ID: D-034 / M-014. Freeze list binds except named graph set. No encoder.
- Pin: `hermes_notes_root` = AGIS MUL. Shadow on. Auto commit+push on a verified one-intent unit; announce first.

## Rollback
- Plugin: `hermes plugins disable aegis-gate`
- D-026: revert pack-first + continuity pack_id. D-029: drop `aegis-flow`.
- D-030: delete 11 factory OS notes; restore retrieval 9.
- D-033: delete 8 research-log notes; revert hub/Ledger wikilinks; restore CORPUS_COUNT=20.
- D-034: delete 4 provenance notes + `cost_provenance.py`; restore CORPUS_COUNT=28; routing withhold unchanged.
- D-031: revert kernel/portable/api/yield + 1.1.1 + FIRST_RELEASE B.
- D-032: revert covering-pack index + last_pack hash verify + freeze doctor checks.
