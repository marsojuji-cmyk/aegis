# Aegis Project Memory

## Architecture
- 1.2.0 agent OS: kernel + portable schema-2 home + frozen `/v1` + yield on 1.1.1 JIT chain.
- Hermes: normalize → policy → redact → allow|deny|require-review → `~/.aegis/guard_log.jsonl`. Rotate: `aegis guard rotate`; tests isolate prod log.
- `savings_percent` = billed USD on `matched_provider_pairs` (else null). Tiny-chat routing on (D-040); implement packs off.
- Hub: `~/AEGIS` (repo|data|skills|vault + `ops/`). Map: `~/AEGIS/00-START-HERE.md`.

## Standing decisions
- D-011: shadow on. Q-011 open. D-013/D-017: live `aegis-gate`.
- D-015/D-016: no pair/`token_delta` until admission + named model.
- D-018/D-021: daemon bind/health. D-019: R-012 at gate. D-020: memory is write.
- D-022–D-029: index/graph/search/sprint/pack_id/skills/Flow.
- D-030 MUL 9→20; D-033/034 20→32. Graph frozen. No MUL thaw D-036/037.
- D-031: 1.2.0 OS. Overlay ≠ SKU. `doctor --product` second-machine floor.
- D-032: covering reuse + hash verify. `os ready`. Honest yield = billed percent matches math.
- D-036: five consecutive real receipts = window ready. Live window READY.
- D-038: 10 same-model pairs, Δcost=0.
- D-039: nano cheaper on tiny chat only. Implement ~17× Pro.
- D-040: explore/review v4-pro → nano (41.3%). Pack/coding_prompt unrouted.
- M-001..M-014: budget modules. `opt_in` fail-closed. Hosted not a SKU. Source mid $45k.
- AA + demo: Pro implement baseline. Clock 2026-09-01; buyer **MARCUS RICHARDS**.
- Last ID: D-040 / M-014. Pin: `hermes_notes_root` = AGIS MUL. Shadow on. Auto commit+push.
- R-014/Q-012: Nous CLI probes fail. R012=`scripts/r012_harness.py`. Bill via `hermes proxy` if no NOUS_API_KEY.

## Rollback
- Plugin: `hermes plugins disable aegis-gate`
- D-026: revert pack-first + continuity pack_id. D-029: drop `aegis-flow`.
- D-030: delete 11 factory OS notes; restore retrieval 9.
- D-033: delete 8 notes; CORPUS=20. D-034: delete 4 notes + classifier; CORPUS=28.
- D-035: revert verify-cost to JSON only. D-036: revert provider_window_status.
- D-039: revert `--governed-model`. D-040: revert `routing.py` + yield billed percent.
- D-031: revert kernel/portable/api/yield. D-032: revert covering-pack + freeze doctor.
