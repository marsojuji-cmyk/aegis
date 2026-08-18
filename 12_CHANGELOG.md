# Changelog

- **2026-08-18**: D-037 live — five consecutive `nous_api` receipts. Window ready. Routing still withheld (2/10 pairs).

- **2026-08-18**: D-036 — `provider_window_status` / `provider_window_ready` on verify-cost. Observe-only. Routing still withheld. No MUL thaw.

- **2026-08-18**: D-035 — `aegis outcome verify-cost` labels gaps (`intentionally_excluded`). Does not authorize routing.

- **2026-08-18**: D-034 — classify four live cost-trust gaps as intentionally_excluded (`local_rehearsal`, `local_cache`). Provenance classifier + tests. Named MUL 28→32. No outcomes.py/guard/wrapper edit. Routing remains withheld.

- **2026-08-18**: D-033 — research-log pilot. Named AGIS MUL thaw 20→28. Deterministic note validator (`research_log.py` + pytest). Cost-trust records cite live `verify-cost`. No CLI. No routing-policy change. No Documents Labs writes.

- **2026-08-18**: Honest product quote (`aegis price quote|skus|pitch`). Replacement-cost + completeness. Token $ is demo only. Hosted is not a SKU.

- **2026-08-18**: D-032 — covering-pack reuse (subset hit, stale bytes miss). Freeze + honest yield on `doctor --product`. `aegis os ready`. No new intel modules. No `savings_percent`.

- **2026-08-18**: Module health CLI (`aegis modules health|measure`). M-001..M-014 map the budget-aware catalog. Ghost `exploratory_enrichment` removed. Autonomy flags fail closed (`opt_in`). Docs no longer claim auto_* defaults true.

- **2026-08-18**: Decision health CLI (`aegis decisions health|measure`). D-021 daemon restarted to 1.2.0. D-030 MUL index rebuilt 9→20. D-014 marked superseded.

- **2026-08-18**: D-031 — Master Aegis 1.2.0 product OS. Agent kernel, portable schema-2 home, frozen `/v1`, hash-cache pack performance, honest yield prove. Default engine `product`. Q-014 answered: overlay ≠ SKU.

- **2026-08-16**: D-030 — named AGIS MUL factory OS graph (9→20) + adversarial validation. Graph growth thawed for that set only.

- **2026-08-16**: D-029 — driver/car/track flow. Perplexity is research-only. Skill `aegis-flow` + Cursor rules. Fifth skill via `--install`.

- **2026-08-16**: D-028 — operating authority. Cursor-only for Aegis. SP-018 closed: git `80f179e` matches claimed 1.1.1. Generated dumps gitignored.

- **2026-08-16**: D-027 — four Cursor skills (`pack-first`, `continuity`, `sprint`, `hermes`) + `--install` copy to `~/.agents/skills`.

- **2026-08-16**: D-026 — capsule `artifacts` pack_id; Cursor pack-first reuse + `--gate`; empty continuity pack fails closed; `reuse=hit|miss` receipt.

- **2026-08-15**: D-025 — sprint ledger (`aegis sprint`) + repo board. Product version strings aligned to 1.1.1. `aegis hermes search|resolve` read-only CLI. Parked items unchanged.

- **2026-08-15**: Q-013 locked-observe — deterministic packet validator; invoke/guard mapping table only. Vault: `Aegis - Semantic Packet Mapping.md`. Repo: `docs/SEMANTIC_PACKET_MAPPING.md`. No encoder. No D-025.

- **2026-08-15**: Q-013 proposed — semantic-swarm parser default (schema → policy → auth). Vault verify: `docs/SEMANTIC_SWARM_VERIFICATION.md`. Claimed `Memory Utility Labs/Aegis - *.md` absent; canonical Labs `08-Research/Architecture/`. No runtime. No D-025.

- **2026-08-15**: D-024 — unified local search (`hermes_search.py`). Read-only over files/notes/projects indexes. No external API.

- **2026-08-15**: D-023 — note-graph skill surface + Memory Utility Labs corpus in AGIS vault `AEGIS/05-Memory-Utility-Labs`. Synthetic + persistent tests. `/Users/ektar/workspace` still empty.

- **2026-08-15**: D-022 — Hermes file indexer (`hermes_index.py`). Gated `read_file` previews + `write_file` of `~/.aegis/hermes_index/files.json`. Brief: `HERMES_ORG_LAYER_BRIEF.md`. `/Users/ektar/workspace` is empty of indexable files.

- **2026-08-15**: D-021 — daemon health polling classifies bindError after stale-PID wipe; failed start reaps; SO_REUSEADDR on router; live :8787 24/24 concurrent health. Suite 248 passed, 1 skipped.

- **2026-08-15**: D-020 — Hermes org-layer catalog (`session_search`, `todo`, skills, projects). `memory` reclassified to `memory.write`. Unknown still fail-closed. See R-015.

- **2026-08-15**: D-019 — R-012 complete at live gate + fail-closed admission. R-014 and Q-012 parked. No Hermes config change. No savings claim.

- **2026-08-15**: Admission CLI is fail-closed. `python3 scripts/r012_admission_gate.py` with no artifact exits 2 and prints `admitted=false`. Silent import is not a pass.

- **2026-08-15**: R-012 admission for `deepseek/deepseek-v4-flash-0731` / `nous` failed (DSML imitation, `tool_call_count=0`). Pair not run. `savings_percent=null`. Plugin re-enabled. Shadow unchanged. See Q-012.

- **2026-08-15**: R-012 live: `aegis-gate` re-enabled. Middleware allow `read_file` + deny `launch_missiles` proven. Token pair not run (D-016). See D-017.
- **2026-08-15**: Hermes token-pair telemetry (`hermes_telemetry.record_pair`). Wired into `scripts/r012_matched_pair.py`. `savings_percent` always null. See R-014.
- **2026-08-15**: Q-008 daemon contract: bind preflight, health states, refuse dual-spawn, bind-fail exit. Suite 243 passed, 1 skipped. See D-018.
- **2026-08-15**: Filled empty `01_CANONICAL_REGISTER.md` as an ID index (R-013).

- **2026-08-14**: Hermes AEGIS wrapper added (`HermesWrapper`). In-repo tool requests are gated (allow/deny/require-review) with redaction and existing guard audit records. Tests: 11 targeted + 221 full suite passed. Shadow mode default unchanged. See D-013.
- **2026-08-14**: R-012 partial: `aegis-gate` enabled in Hermes via symlink + `hermes plugins enable --no-allow-tool-override`. Live middleware probe: 1 allow, 1 deny, exception did not bypass. Token benchmark not run. See D-014.
- **2026-08-14**: R-012 LLM pair attempted (`hermes -z`, file toolset). Nous flash pair completed without executing tools; ΔT=13 not interpretable. Ollama retry blocked by 64k context rule. No savings percentage. See Q-012.
- **2026-08-14**: Q-012 screen: glm-5.2, hy3:free, solar-pro4:free all ≥64k but `tool_call_count=0`. Matched pair not started. No savings percentage.
- **2026-08-14**: R-012 admission gate (`scripts/r012_admission_gate.py` + tests). Invalid pairs cannot emit token_delta. No model probe. D-015.
- **2026-08-14**: R-012 paused at admission gate (D-016). No pair until authorized compatible model.
- **2026-08-14**: hermes-aegis stop. `aegis-gate` disabled via official plugin command. Symlink and repo code left in place. Shadow mode unchanged.
- **2026-08-14**: R-012 measurement mission stopped on baseline mismatch: plugin disabled (`enabled: []`). No pair, no savings claim, no policy change.
