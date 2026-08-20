# Aegis Project Memory

## Architecture
- 1.2.0 agent OS: kernel + portable schema-2 home + frozen `/v1` + yield on 1.1.1 JIT chain.
- Hermes: normalize → policy → redact → allow|deny|require-review → `~/.aegis/guard_log.jsonl`.
- `savings_percent` null unless admitted pair. Sprints: `aegis sprint`. Pack-first; `reuse=hit` → no packed_path re-read.
- Hub: `~/AEGIS` (repo|data|skills|vault symlinks + real `ops/` ex-`Desktop/AGEIS`). Finder tags `AEGIS`+5 category. Map: `~/AEGIS/00-START-HERE.md`.

## Standing decisions
- D-011: shadow on. Q-011 open. D-013/D-017: live `aegis-gate`.
- D-015/D-016: no pair/`token_delta` until admission + named model.
- D-018/D-021: daemon bind/health. D-019: R-012 at gate. D-020: memory is write.
- D-022–D-029: index/graph/search/sprint/pack_id/skills/Flow.
- D-030 MUL 9→20; D-033/034 20→32. Graph frozen. No MUL thaw D-036/037.
- D-031: 1.2.0 OS. Overlay ≠ SKU. `doctor --product` second-machine floor.
- D-032: covering reuse + hash verify. `os ready`. Freeze+honest yield on doctor.
- D-036: five consecutive real receipts = window ready, not routing. Live window READY.
- D-038: 10 billed matched pairs, same model. Δcost=0. Routing withheld.
- D-039: nano cheaper only on tiny chat. Implement pack: Pro $0.00005 vs nano $0.00085 (~17×). Routing off.
- M-001..M-014: budget modules. Ghost enrichment removed. `opt_in` fail-closed.
- Price: source mid $45k. Exclusive ~$108k lockout — refuse if year-1 $300k (7× source). Hosted not a SKU.
- AA + demo: frozen honesty beat. Pro implement baseline. Clock 2026-09-01; buyer **MARCUS RICHARDS** (MUL founder, AEGIS creator).
- Last ID: D-039 / M-014. Freeze list binds except named graph set. No encoder.
- Pin: `hermes_notes_root` = AGIS MUL. Shadow on. Auto commit+push on a verified unit.
- R-014/Q-012: user authorized 2026-08-19. Nous CLI probes fail (DSML/XML, tool_call_count=0). R012 harness default=agent loop (`scripts/r012_harness.py`). Bill via `hermes proxy` when NOUS_API_KEY unset.

## Rollback
- Plugin: `hermes plugins disable aegis-gate`
- D-026: revert pack-first + continuity pack_id. D-029: drop `aegis-flow`.
- D-030: delete 11 factory OS notes; restore retrieval 9.
- D-033: delete 8 notes; CORPUS=20. D-034: delete 4 notes + classifier; CORPUS=28.
- D-035: revert verify-cost to `cost_verification_report` JSON only.
- D-036: revert `provider_window_status` + `provider_window_ready`.
- D-039: revert `--governed-model`; withhold flags on verify-cost unchanged.
- D-031: revert kernel/portable/api/yield + 1.1.1. D-032: revert covering-pack + freeze doctor.
