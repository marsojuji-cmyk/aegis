# Status report — Burn reliability milestone (v1.1.1+)

## Standing section: Burn health

| Metric | Value / note |
|--------|----------------|
| **Level** | `ok` · `caution` (≥80% safe) · `warn` (≥100%) · `critical` (≥125%) |
| **Safe daily** | Tokens/day that keep week-end ≥ reserve floor |
| **Avg daily burn** | From personal usage intel (noise-filtered ledger) |
| **Ratio** | `avg_daily_burn / safe_daily` |
| **Config SSOT** | `burn_caution_multiplier`, `burn_warn_multiplier`, `burn_warning_multiplier` |
| **Surfaces** | Menu bar · Dashboard · Weekly report · `GET /v1/aegis/burn` · `aegis intel burn` |
| **Events** | `~/.aegis/burn_events.jsonl` (cross / recover) |
| **Budget-aware** | Soft worker cap when warn/critical (`budget_aware_mode`) |

### Completed this milestone

- [x] Progressive burn levels (80% / 100% / 125%) with tone + recommended actions  
- [x] Config-driven thresholds (change TOML → all consumers move)  
- [x] Multi-surface fan-out: menu bar, dashboard, weekly **Burn health** table  
- [x] Live endpoint `GET /v1/aegis/burn` + CLI `aegis intel burn`  
- [x] Threshold cross / recovery event log  
- [x] Load-test script `scripts/load_test_burn.py`  
- [x] Soft budget-aware batch workers  

### Critical copy (125%+)

> Daily burn … is ~N% over safe allowance …/day (threshold 125% of safe).  
> **Cut fan-out: fewer parallel tasks and smaller batches.**

### Budget-Aware Mode (shipped)

See **`docs/BUDGET_AWARE.md`**. Reactive burn warnings are now a **proactive control loop**:

- Sticky bands with hysteresis (`budget_recovery_hysteresis`)
- Module ranking + shed/throttle/prefer-cheap policies
- Tick gating (never-shed critical path)
- Fan-out: menu bar · dashboard · weekly **Budget-Aware Mode** section
- `aegis intel budget` · `GET /v1/aegis/budget-aware` · dry-run / simulate

### Follow-on workstream

1. Instrument hit rates at 80/100/125% across real weeks (false-positive review).  
2. Token-weighted top consumers (not count-only).  
3. Learned ROI weights for module ranking (replace static scores).  
4. Offline/degraded path with last-known safe_daily.  
5. Portfolio packaging: “config threshold + multi-surface fan-out + budget-aware shed” pattern.  

### 5-minute weekly burn review checklist

1. `aegis intel burn` — note level + ratio.  
2. Skim `~/.aegis/burn_events.jsonl` for unexpected critical spikes.  
3. Confirm weekly report **Burn health** section matches CLI.  
4. If critical: cut fan-out; re-check after 1 day of average.  
5. If false positive: adjust multipliers in `config.toml` only.

### Contract (Intelligence Layer → consumers)

| Field | Meaning |
|-------|---------|
| `level` | Progressive band |
| `message` | Human copy (identical across surfaces) |
| `fix` / `fix_detail` | Recommended action |
| `burn_warning` | Present only when `level == critical` (back-compat) |
| `bands` | Numeric thresholds from config |
| `budget_aware.recommended_workers` | Soft fan-out cap |
