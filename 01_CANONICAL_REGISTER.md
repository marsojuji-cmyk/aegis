# Canonical Register

Index only. Detail lives in the specialized file named by each ID.
Updated: 2026-08-18. Empty file filled from existing evidence (R-013).

## Decisions (02_DECISION_LOG.md)

| ID | Status | Summary |
|---|---|---|
| D-011 | active | Shadow-mode observation only. No hard-block / threshold tune. |
| D-012 | active | 100-request baseline archived; official thresholds blocked. |
| D-013 | active | Hermes tool requests pass `HermesWrapper` (allow/deny/require-review). |
| D-014 | superseded | Enable path defined; live enable is D-017. |
| D-015 | active | Admission gate required before any token_delta. |
| D-016 | active | No LLM pair until user names model+provider. |
| D-017 | active | 2026-08-15: `aegis-gate` enabled; live middleware allow+deny proven. |
| D-018 | active | Daemon bind preflight + health states + refuse dual-spawn. |
| D-019 | active | Park R-014 savings; R-012 complete at gate/admission only. |
| D-020 | active | Hermes org tools catalogued; memory is write, not read. |
| D-021 | active | Daemon health/bindError/reap + live concurrent /healthz. |
| D-022 | active | Gated file indexer → `~/.aegis/hermes_index/files.json`. |
| D-023 | active | Note graph + four skills; MUL vault corpus; empty default root valid. |
| D-024 | active | Unified local search over gated indexes. No external API. |
| D-025 | active | Sprint ledger is CLI SoT (`aegis sprint`). Board is the human index. |
| D-026 | active | Capsule pack_id + Cursor pack-first gate + empty-pack refuse. |
| D-027 | active | Four Cursor skills installed via `aegis cursor --install`. |
| D-028 | active | Aegis is shot-caller. Cursor-only for Aegis. One active sprint. Git ledger first. |
| D-029 | active | Flow: driver / Cursor+Perplexity car / One track. Skill `aegis-flow`. |
| D-030 | active | Named AGIS MUL factory OS graph (9→20). Graph growth thawed for that set only. |
| D-031 | active | Master Aegis 1.2.0 product OS. Kernel + portable home + frozen /v1 + yield harness. Q-014: overlay ≠ SKU. |
| D-032 | active | Covering-pack reuse with hash verify. Freeze+honest yield on `doctor --product`. `aegis os ready`. |
| D-033 | active | Named AGIS MUL research-log cluster (20→28). Cost-trust observe-only. No routing change. |
| D-034 | active | Four D-033 gaps classified intentionally_excluded. Classifier only. Routing still withheld. |
| D-035 | active | verify-cost CLI emits classifications. routing_authorized forced false. |
| D-036 | active | Five consecutive provider receipts are a ready precondition. Routing still withheld. |
| D-037 | active | collect-receipts CLI: env key + billed USD only. Probe default. Routing still withheld. |
| D-038 | active | 10 billed matched pairs, same model. Δcost=0 so routing still withheld. |
| D-039 | active | Cheaper governed nano vs v4-pro. Pair workflow eligible. Product routing still off. |

## Risks (03_RISK_REGISTER.md)

| ID | Status | Summary |
|---|---|---|
| R-010 | mitigated-in-code | Socket/health fragility; startup contract now classified. |
| R-011 | mitigated | v1 missing-field ledger archived. |
| R-012 | complete-at-gate | Live allow+deny + admission framework. Measurement parked. |
| R-013 | mitigated | This register was empty; now an index only. |
| R-014 | parked | No admitted pair. Resume only with authorized native-tool model. |
| R-015 | open | Memory writes are not domain-scoped to the Hermes store. |

## Questions (04_OPEN_QUESTIONS.md)

| ID | Status | Summary |
|---|---|---|
| Q-008 | answered | Test bind/health as classified states; do not ignore the module. |
| Q-009 | resolved | v1 archive split. |
| Q-010 | resolved | Enable via symlink + `hermes plugins enable`. |
| Q-011 | open | When should require-review become a hard block? (blocked by D-011) |
| Q-012 | parked | No configured native-tool-call model. Do not probe leftovers. |
| Q-013 | locked-observe | Deterministic validator. Mapping observe-only. No D-025. |
| Q-014 | answered | Factory OS overlay stays MUL graph. Product SKU is 1.2 kernel program (D-031). |
| Q-015 | open | When to require the six-field consequential-action envelope on live tools? |
| Q-016 | open | Corporate hierarchy: catalog only, or role runtime? Blocked on R-015. |

## Sprints (05_SPRINT_BOARD.md)

| ID | Status | Summary |
|---|---|---|
| SP-001 | done | Sprint reporting CLI + jsonl + board. |
| SP-002 | done | Align product version strings to 1.1.1. |
| SP-003 | done | `aegis hermes search\|resolve` read-only CLI. |
| SP-010 | parked | R-014 admitted pair (D-015/D-016/Q-012). |
| SP-011 | blocked | Q-011 hard-block (D-011). |
| SP-012 | parked | Q-013 encoder (locked-observe). |
| SP-013 | done | Capsule artifacts pack_id (D-026). |
| SP-014 | blocked | R-015 memory domain scope. |
| SP-015 | done | Cursor pack-first gate + hit/miss receipt. |
| SP-016 | done | Empty continuity pack fails closed. |
| SP-017 | done | Four Cursor skills + `--install`. |
| SP-018 | done | Align git ledger to claimed 1.1.1. No new surface. |
| SP-019 | done | Driver/car/track flow + `aegis-flow` skill. |
| SP-020 | done | Factory OS MUL graph + adversarial validation (D-030). |
| SP-021 | done | Master Aegis 1.2.0 product OS (D-031). |
| SP-023 | done | Release program: covering reuse + os ready (D-032). |

## Modules (`aegis modules health`)

Budget-aware catalog. No prior M- register existed; IDs are the live modules.

| ID | Status | Name | Summary |
|---|---|---|---|
| M-001 | active | surplus_sync | Never-shed surplus sync. Does not auto-spend. |
| M-002 | active | usage_intel | Week usage + waste signals. Not official thresholds. |
| M-003 | active | forecast | Projected remaining / hard_stop freeze. |
| M-004 | active | burn_status | Daily/safe ratio. Headroom-to-floor, not leftover cap. |
| M-005 | active | weekly_report | Never-shed report from explicit tick/CLI. |
| M-006 | parked | policy_nudges | Off unless `auto_apply_fixes`. |
| M-007 | active | cache_optimize | Sheddable cache learn/prune. |
| M-008 | parked | auto_invest | Frozen. `opt_in` fail-closed. |
| M-009 | parked | auto_queue_ideas | Armed only if invest or apply-fixes is on. |
| M-010 | active | seed_ideas | Idempotent three-title starter seed. |
| M-011 | parked | memory_capture | Off unless `auto_memory`. R-015 open. |
| M-012 | parked | cross_model_memory_inject | Router inject gated on `auto_memory`. |
| M-013 | superseded | exploratory_enrichment | Removed from catalog; never had a runtime. |
| M-014 | active | continuity_bridge | Auto-fires only on emergency band. |

## Continuity

Latest: `10_CONTINUITY_SNAPSHOT.md` (2026-08-15 addendum).
