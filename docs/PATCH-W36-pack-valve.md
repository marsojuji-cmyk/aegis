# PATCH-W36 — Close the pack write valve at zero headroom

**Status:** spec + verifier matrix (pre-W36)  
**Owner:** Cursor (implementation cortex)  
**Approval gate:** Marc required only if cap, floor, ownership, or reserve-flow architecture changes  
**Tank model:** unchanged — two meters only (`remaining`, `surplus`)

## Problem (verified control defect)

Preflight and `aegis pack` currently **assemble → ledger write → then** signal `hard_stop` / exit 4. The freeze is a warning after spend, not a valve. Under `headroom == 0`, fresh pack misses must not append ledger rows with `processed_in > 0`.

Separate lie: when `safe_daily == 0`, burn status must not emit “Burn healthy.”

## Non-goals (do not implement)

- Mid-week refill of `remaining` from savings, reuse, or land-shrink
- Third meter or “flow into reserve” pipe
- Raising `weekly_token_cap`, lowering `reserve_floor`, or deleting ledger rows
- Crediting reuse hits onto `remaining` (reuse keeps `processed_in = 0`; remaining does not rise)

## Definitions (unchanged)

| Meter | Formula / rule |
|-------|----------------|
| `remaining` | `(cap − consumed) / cap` — falls on pack miss; Monday refill only |
| `surplus` | savings × `reinvest_rate` — wish jar; mints only when `remaining ≥ reserve_floor` |
| `headroom` | `max(0, cap − processed − cap×reserve_floor)` — spendable above floor |
| `reuse_hit` | `processed_in = 0` — allowed even at `headroom == 0` |

## Patch specification (Cursor, post-W36)

### 1. `fund.py` — headroom SSOT

Add pure helpers (no side effects):

- `compute_spend_headroom(cfg, report=None) -> int`
- `pack_write_allowed(*, reuse: bool, ...) -> tuple[bool, str]`

Rule: `reuse=True` always allowed; fresh pack miss refused when `headroom <= 0`.

### 2. `preflight.py` — valve before write

In `_do_pack`, **before** `assemble` / `record` / `save_pack` on cache miss:

- Call `pack_write_allowed(reuse=False)`
- If refused: return `exit_code=4`, no ledger row, no pack file write
- Reuse path unchanged (`reuse_hit`, `processed_in=0`)

In `run_preflight`:

- `ok=False`, `exit_code=4` when refused
- Error copy: `headroom=0 reserve=<signal> — pack write refused (reuse-only until week rolls)`

### 3. `cli.py` — `_cmd_pack` parity

Same guard on cache miss path (after reuse branch, before assemble). Exit **4**, stderr message, no `record(kind="pack")`, no `save_pack`.

### 4. `burn.py` — zero safe_daily copy

When `recommended_daily_budget <= 0`:

- `level = "critical"`
- `ok = False`
- Message: no spend headroom; reuse-only until week rolls
- Must **not** contain “healthy” or “Burn healthy”

### 5. `forecast.py` — advice line

When `safe_daily <= 0`, advice must not say “Stay ≤ 0 …”; use reuse-only wording.

### Files touched

```
src/aegis/fund.py
src/aegis/preflight.py
src/aegis/cli.py
src/aegis/burn.py
src/aegis/forecast.py
tests/test_pack_headroom.py
```

## Verifier test matrix (Evidence Verifier — decision-grade gate)

Run: `python3 -m pytest tests/test_pack_headroom.py tests/test_burn.py tests/test_preflight_output.py -q`

| ID | Case | Setup | Action | Expected |
|----|------|-------|--------|----------|
| V-01 | headroom math | cap=1M, floor=0.80, consumed=0 | `compute_spend_headroom()` | 200_000 |
| V-02 | headroom math spent | cap=1M, consumed=50k | `compute_spend_headroom()` | 150_000 |
| V-03 | pack refused | cap=1k, floor=0.80, consumed=900 | `aegis pack` (miss) | exit 4; no new `kind=pack` row |
| V-04 | reuse allowed | seed cache healthy; then headroom=0 | `aegis pack` (hit) | exit 0; `reuse_hit`, `processed_in=0` |
| V-05 | preflight refused | headroom=0 | `run_preflight` explore miss | `ok=False`, exit 4, no pack row |
| V-06 | burn copy | forecast `safe_daily=0` | `burn_status()` | `level=critical`, `ok=False`, no “healthy” |
| V-07 | API gate | headroom=0 | `pack_write_allowed(reuse=False)` | `(False, reason)` |
| V-08 | API reuse | headroom=0 | `pack_write_allowed(reuse=True)` | `(True, "")` |
| V-09 | regression explore | healthy ledger | `run_preflight` explore | `ok=True`, exit 0 (existing test) |
| V-10 | regression burn bands | safe=1000, burn=1400 | `burn_status()` | `level=critical`, fan-out copy |

### Handoff chain (unchanged)

Collector → Analyst → **Verifier (V-01…V-10)** → PM → Report Writer → Archivist

Verifier signs off only when all matrix rows pass on a clean `AEGIS_HOME` fixture.

## Operational sequence

| When | Action |
|------|--------|
| **Today (W35 hard_stop)** | Do not run Cursor `pack` / `preflight`. Reuse-only reads. |
| **Monday** | Weekly `remaining` refill. Spend ≤ processed ceiling (verify cap with Marc if changing). Then surplus may mint if `remaining ≥ floor`. |
| **After W36** | Land patch; Verifier runs matrix; no tank-model edits without Marc. |

## Unverified claims (do not treat as spec inputs)

Until ledger/packet artifacts are located: “49,493 tokens booked under hard_stop,” “698k consumed,” “30.19% remaining,” “8% reuse hit rate,” W35/W36 calendar outcomes.
