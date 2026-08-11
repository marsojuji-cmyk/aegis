# Budget-Aware Mode

Proactive control loop on top of progressive burn bands.  
**Detect → adapt → preserve high-ROI signal** instead of only warning.

## Bands (config SSOT)

| Band | Burn level | Default ratio | Behavior |
|------|------------|---------------|----------|
| `ok` | ok | &lt; 0.80 | Full capacity |
| `caution` | caution | ≥ 0.80 | Prefer cheap sources; light throttle |
| `adaptive` | warn | ≥ 1.00 | Reduce frequency; shed low-priority modules |
| `emergency` | critical | ≥ 1.25 | Minimal viable intel; cut fan-out |

```toml
budget_aware_mode = true
budget_recovery_hysteresis = 0.10
budget_use_projection = true
burn_caution_multiplier = 0.80
burn_warn_multiplier = 1.00
burn_warning_multiplier = 1.25
```

## Mechanisms

1. **Module ranking** — cost · signal quality · freshness · consumer priority  
2. **Never-shed set** — surplus, usage, forecast, burn, weekly report  
3. **Frequency scaling** — 1.0 → 0.75 → 0.5 → 0.0 (critical path degrades slower)  
4. **Graceful shed** — skip work; mark stale-ok; audit in events log  
5. **Hysteresis** — only demote after ratio falls `entry − hysteresis`  
6. **Projection** — early escalate if week-end projection is throttle/hard_stop  
7. **Source preference** — live→cache→reuse→mock order flips under pressure  

## CLI / HTTP

```bash
aegis intel budget
aegis intel budget --dry-run
aegis intel budget --simulate adaptive
aegis intel budget --json
```

```
GET /v1/aegis/budget-aware
GET /v1/aegis/budget-aware?dry_run=1
GET /v1/aegis/budget-aware?simulate=emergency
```

## Surfaces

- **Menu bar** — `Budget: Adaptive – N shed, M reduced`
- **Dashboard** — panel: band, shed list, workers cap
- **Weekly report** — **Budget-Aware Mode** section + transitions
- **Events** — `~/.aegis/budget_aware_events.jsonl`

## Contract (consumers)

| Field | Meaning |
|-------|---------|
| `band` | ok \| caution \| adaptive \| emergency |
| `menu_summary` | Single-line fan-out copy |
| `modules_shed` / `modules_throttled` | What was reduced |
| `recommended_workers` | Soft batch cap |
| `source_preference` | Ordered source policy |
| `plan.decisions[]` | Per-module audit |

## Continuity Bridge (emergency privileged action)

When band → **emergency**, tick auto-generates a Continuity Bridge Report
(`aegis.continuity`) under `~/.aegis/continuity/`:

- Full handoff markdown (ledger, resume protocol, KPIs, Cross-AI next steps)
- Semantic embedding pack (`embedding_handoff_*.json`) with integrity hash
- Manual: `aegis intel continuity` · API: `GET /v1/aegis/continuity`

See `docs/CONTINUITY.md`.

## Acceptance criteria

- [x] Config disables entire mode (`budget_aware_mode = false` → always ok)  
- [x] Hysteresis prevents thrash near 100%  
- [x] Never-shed modules still run in emergency  
- [x] Dry-run / simulate do not stick state  
- [x] Tick actions include budget summary + shed list  
- [x] Weekly report documents band decisions  
