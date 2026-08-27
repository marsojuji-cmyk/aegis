# Aegis Intelligence Layer (v1.1.1)

Autonomous token economy: **savings → surplus credits → highest-ROI moves → more savings**.

**Status:** production-hardened (atomic state/memory/cache IO, idempotent policy nudges, partial-failure ticks, reserve-gated invest).

## Loop

```
ledger spend  →  usage intel  →  waste signals
      ↓                              ↓
 surplus mint  ←  reserve OK  ←  predictive budget
      ↓
 auto-queue ideas  →  auto-invest grade≥B  →  policy fixes
      ↓
 self-optimizing cache  +  cross-model memory  +  weekly ROI report
```

## Modules

| Module | Role |
|--------|------|
| `usage_intel.py` | Personal usage + waste signals (noise-filtered) |
| `forecast.py` | Predictive weekly budget / safe daily burn |
| `intelligence.py` | Compound `tick()` + bg loop |
| `memory.py` | Cross-model memory (locked, capped, atomic) |
| `cache_optimizer.py` | Hit/miss stats, learned fallbacks, cold prune |
| `policy_nudges.py` | Idempotent config course-correction |

## Autonomy flags (`~/.aegis/config.toml`)

| Key | Default | Role |
|-----|---------|------|
| `auto_tick` | false | Background compound ticks with router (opt-in) |
| `auto_invest` | false | Fund top ROI ideas from surplus (frozen until thawed) |
| `auto_apply_fixes` | false | Nudge pack/output policy from signals (opt-in) |
| `auto_memory` | false | Capture/inject cross-model memory (opt-in; R-015 open) |
| `intel_tick_seconds` | 300 | Tick interval while daemon runs |
| `min_roi_grade_auto` | B | Minimum grade to auto-invest |
| `cache_hit_threshold` | 30 | Forecast warn when cache hit % is below this |
| `burn_caution_multiplier` | 0.80 | Subtle burn indicator (ratio of safe daily) |
| `burn_warn_multiplier` | 1.00 | At/over safe daily allowance |
| `burn_warning_multiplier` | 1.25 | Critical — ≥25% over safe; cut fan-out |
| `budget_aware_mode` | true | Proactive shed/throttle control loop |
| `budget_recovery_hysteresis` | 0.10 | Demote sticky band only after ratio falls this far |
| `budget_use_projection` | true | Early escalate if week-end projection is hot |

Reserve floor (≥80%) always wins — invest freezes on throttle/hard_stop.

## CLI

```bash
aegis intel status
aegis intel tick --force-report
aegis intel forecast
aegis intel burn
aegis intel budget [--dry-run] [--simulate adaptive]
aegis intel usage
aegis intel report
python3 scripts/load_test_burn.py   # walk 80/100/125% bands
```

## HTTP (router)

- `GET /v1/aegis/intel` — full intelligence status
- `GET /v1/aegis/forecast` — predictive budget (+ `burn_status`)
- `GET /v1/aegis/burn` — live burn health (levels, events, workers)
- `GET /v1/aegis/budget-aware` — band plan, shed list, simulate/dry_run
- `POST /v1/aegis/intel/tick` — run one compound cycle

## Data plane

| Path | Role |
|------|------|
| `~/.aegis/intel_state.json` | Tick counters / last actions |
| `~/.aegis/memory.jsonl` | Cross-model memory |
| `~/.aegis/cache_stats.json` | Hit/miss + learned fallbacks |
| `~/.aegis/reports/weekly_*.md` | Weekly ROI report |

## Product surfaces

- **Menu bar shield** — live reserve + forecast + burn/safe + fan-out warning
- **Dashboard** — full burn warning card (25% over safe → cut parallel/batch size)
- **Ledger** — deep dive on every token txn
- **Weekly report** — ROI + **Burn & fan-out** section under `reports/`
