# Continuity Snapshot — 2026-08-14 Hermes AEGIS wrapper

status: verified for in-repo gate; Hermes runtime wiring not installed
artifact: `src/aegis/wrappers/hermes_wrapper.py`
action: completed smallest usable Hermes → AEGIS control path
timestamp: 2026-08-14
scope: `/Users/a100/Projects/aegis`

## Verified

- Before this change, the repo had `AegisGuard` + OpenAI/Anti-Gravity LLM wrappers. No Hermes tool gate existed (`rg hermes` in `src/` was empty except outcome `cost_source`).
- `HermesWrapper.handle()` is the single in-repo execution entry: normalize → ids → classify → policy/mission-lock → redact → allow|deny|require-review → optional execute → `GuardDecision` JSONL.
- Targeted tests: `python3 -m pytest tests/test_hermes_wrapper.py -q` → 11 passed.
- Full suite: `python3 -m pytest -q` → 221 passed.
- Default `guard_shadow_mode=true` was not disabled (D-011 preserved).
- Existing `AegisGuard` behavior was not rewritten.

## Flow (enforced in-repo)

1. Normalize incoming request (object, tool, args, identity, scope).
2. Assign `request_id` and `trace_id`.
3. Classify capability/risk from the explicit catalog; unknown → deny.
4. Policy: known agent, explicit allowed domains, mission lock, high-risk → review.
5. Redact secret keys/patterns before audit excerpts.
6. Fail closed on unknown identity, scope, capability, malformed/ambiguous action.
7. Execute only on `allow`, or shadow-observe `require-review`.
8. Persist via existing `AegisGuard._record_decision` / `~/.aegis/guard_log.jsonl`.
9. Return structured `{decision, reason, request_id, trace_id, would_block, executed, ...}`.
10. Hermes plugin middleware must not raise on deny (runtime is fail-open).

## Files changed

- `src/aegis/wrappers/hermes_wrapper.py` — gate
- `src/aegis/wrappers/__init__.py` — export
- `src/aegis/cli.py` — `aegis wrap --provider hermes`
- `integrations/hermes/plugin.yaml` — plugin metadata
- `integrations/hermes/__init__.py` — register glue
- `tests/test_hermes_wrapper.py` — adversarial tests
- `02_DECISION_LOG.md` — D-013
- `03_RISK_REGISTER.md` — R-012, R-013
- `04_OPEN_QUESTIONS.md` — Q-010, Q-011

## Not installed / not tested

- Enabling the plugin inside `~/.hermes/hermes-agent` (outside repo; R-012).
- Live Hermes Desktop/CLI tool call through this gate.
- Daemon host-permission suite (Q-008 / R-010 still open).
- Disabling shadow mode or changing guard thresholds.

## Next (Hermes / Antigravity / Grok Build)

Highest remaining leverage: enable `integrations/hermes` in the Hermes runtime so the fail-open tool path cannot skip this gate. Do not start a second initiative until that wiring is authorized.

---

# Continuity addendum — 2026-08-14 R-012 live wiring

status: plugin enabled; live middleware probe verified; token savings unmeasured
artifact: `~/.hermes/plugins/aegis-gate` → `integrations/hermes`
action: enable plugin; prove one allow and one deny on Hermes middleware
evidence: `hermes plugins list --user` shows `enabled user 1.0.0 aegis-gate`; `scripts/probe_hermes_runtime.py` ok=true; suite 221 passed
timestamp: 2026-08-14

## Verified this addendum

- Plugin enabled in `~/.hermes/config.yaml` (`plugins.enabled: [aegis-gate]`, `allow_tool_override: false`).
- Allowed `read_file` through `run_tool_execution_middleware` invoked `next_call` (3.837 ms).
- Denied `launch_missiles` returned `blocked_by=aegis` and did not invoke `next_call` (0.731 ms).
- Raising middleware before the gate did not invoke `next_call`; gate still denied.
- `hermes_tool_execution` did not raise on garbage input.
- Shadow mode / thresholds unchanged. Full suite still 221 passed.
- Token efficiency: **not measured**. No LLM session. No savings percentage.

## Still not tested

- Hermes Desktop / `hermes chat` live tool call.
- Before/after tokens per task, retries, blocked-work tokens, useful-output ratio.
- Empty-scope live Desktop traffic (will fail closed until `guard_allowed_domains` is set).

## Next

Do not start another feature. Next authorized measurement: one Desktop/LLM task pair with token counts. Do not disable shadow mode.

---

# Continuity addendum — 2026-08-14 R-012 measurement attempt

status: observed — token fields present; pair not comparable
artifact: `/tmp/aegis-r012-measure/mission-pair-report.json`
action: official disable/enable control + gated oneshot (`-t file --yolo`)
timestamp: 2026-08-14T17:43:30-0600

## Observed

- Probe (Hermes 3.11): allow `read_file` next_call=true 3.077ms; deny `launch_missiles` next_call=false; exception path still deny; garbage did not raise.
- Targeted: `tests/test_hermes_wrapper.py` 11 passed.
- Control/treatment both printed XML `<tool_call><read_file>…` and never invoked the file tool. Marker not returned. `success=false` both sides.
- Usage-file tokens exist (control 3661 / treatment 1799). Treatment cache_read=1408. `hermes_guard_records=[]`. Delta is cache/turn variance, not AEGIS prevented work.
- Plugin restored: `enabled user 1.0.0 aegis-gate`. Production `guard_shadow_mode=true`, domains empty, thresholds unchanged.
- Hermes-agent source not edited. `package-lock.json` remains dirty.
- Full-suite claim of 221 was **not** re-run. `ci_product_suite_record.md` still records 201.

## Not a savings result

`savings_percent` remains null. R-012 stays measurement-open. Do not generalize. Do not change policy.

---

# Continuity addendum — 2026-08-14 hermes-aegis stop

status: observed
artifact: `hermes plugins disable aegis-gate`
action: live gate stopped; symlink and repo integration left in place
timestamp: 2026-08-14
evidence: `hermes plugins list --plain --no-bundled` → `disabled user 1.0.0 aegis-gate`; symlink still `~/.hermes/plugins/aegis-gate` → `integrations/hermes`; `guard_shadow_mode=true`; domains empty
limitations: disable takes effect on the next Hermes session; running Hermes.app was not killed
rollback: `hermes plugins enable aegis-gate --no-allow-tool-override`

---

# Continuity addendum — 2026-08-14 R-012 LLM pair

status: measurement-incomplete; no savings claim
artifact: `/tmp/aegis-r012-measure/pair-1-nous-report.json` + `scripts/r012_matched_pair.py`
action: one matched `hermes -z` pair; one invalid local retry
timestamp: 2026-08-14

## Verified

- Pair 1 model/provider: `stepfun/step-3.7-flash:free` / `nous`. Same prompt, `-t file`, `--ignore-rules`, `--reasoning none`.
- Ungated: 1952 in / 69 out / 2021 total / 1 API call / 7.79s / session `20260814_173928_3192ac`.
- Gated: 288 in + 1664 cache_read / 56 out / 2008 total / 1 API call / 5.2s / session `20260814_173936_9d46d0`.
- Both `completed=true`, both `success=false` (marker not in stdout).
- Gate not exercised: `hermes_guard_records=[]`.
- ΔT total = 13 tokens = cache reuse, **not** AEGIS savings.
- Pair 2 (`qwen2.5-coder:7b` / `ollama-launch`) aborted: Hermes minimum 64k context. No config change made to bypass this.
- Plugin left enabled. Production `~/.aegis/config.toml` has no `guard_allowed_domains` change. Shadow/thresholds unchanged.
- `savings_percent`: null.

## Not a valid efficiency result

A gated run with fewer billed input tokens that fails the task is not an improvement. The gate never saw a tool call.

## Next

Need a 64k+ model that performs native Hermes tool calls (Q-012). Then repeat **one** pair. Do not disable shadow. Do not publish a percentage.

---

# Continuity addendum — 2026-08-14 Q-012 screen, pair not started

status: no efficiency conclusion; available ≥64k Nous models incompatible with native Hermes tool-call path
artifact: `/tmp/aegis-r012-measure/compatibility-20260814.json`
action: preflight + compatibility probes only; matched pair not run
timestamp: 2026-08-14

## Verified context (Hermes `get_model_context_length`)

- `z-ai/glm-5.2` 1048576
- `tencent/hy3:free` 262144
- `upstage/solar-pro4:free` 524288
- `stepfun/step-3.7-flash:free` 262144
- All ≥ `MINIMUM_CONTEXT_LENGTH` 64000

## Probes (plugin disabled; fixture `/tmp/aegis-r012-measure/marker.txt` = `R012-MARKER-7c3e91`)

| model | session | tool_call_count | marker | native |
|---|---|---:|---|---|
| z-ai/glm-5.2 | 20260814_174335_a254b6 | 0 | false (guessed `R012-MEASURE-ACTIVE`) | false |
| tencent/hy3:free | 20260814_174355_ff9dd8 | 0 | false (hallucinated ENOENT) | false |
| upstage/solar-pro4:free | 20260814_174413_83eb93 | 0 | false (vendor `<\|tool_call:start\|>`) | false |

Pair not started. Plugin re-enabled. Production domains unchanged. Shadow/thresholds unchanged. `savings_percent=null`.

---

# Continuity addendum — 2026-08-14 R-012 admission gate

status: gate prepared; no compatible model; no pair
artifact: `scripts/r012_admission_gate.py`
action: encode 10-point admission checklist; refuse token delta on invalid pairs
evidence: `python3 -m pytest tests/test_r012_admission_gate.py -q` → 9 passed
timestamp: 2026-08-14

No model probes this turn. Plugin remains enabled. Production scope unchanged. `savings_percent=null`.
Next: await authorization and access to a verified compatible model.

---

# Continuity addendum — 2026-08-14 R-012 PAUSED

status: paused at admission gate
artifact: `scripts/r012_admission_gate.py`
action: none (no pair, no probe, no billing)
timestamp: 2026-08-14
token_delta: null
savings_percent: null
efficiency_result: not_tested
plugin: enabled
shadow_mode: on
production_guard_allowed_domains: unchanged

## Resume only when all are true

1. Specific model and provider identified.
2. User authorized access if payment or account changes are required.
3. Verified context length ≥ 64000.
4. Hermes accepts the model.
5. Native Hermes tool call demonstrated.
6. `read_file` executes against `/tmp/aegis-r012-measure`.
7. `R012-MARKER-7c3e91` returned exactly.
8. Treatment records `gate_observed=true`.
9. Control and treatment expose comparable token metadata.

## Resumption procedure

1. Set `R012_MODEL` and `R012_PROVIDER` explicitly.
2. Run the admission gate first.
3. Stop immediately if admission fails.
4. Run exactly one matched pair via `scripts/r012_matched_pair.py`.
5. Do not publish `savings_percent`. Set `token_delta=null` unless both sides admit.

Until then: await authorization and access to a verified compatible model.

---

# Continuity addendum — 2026-08-14 R-012 measurement mission STOP

status: observed — baseline mismatch; no new pair
artifact: `hermes plugins list --user`; `scripts/probe_hermes_runtime.py` (Hermes venv)
action: verify handoff; stop; no plugin enable; no LLM pair
timestamp: 2026-08-14
token_delta: null
savings_percent: null
efficiency_result: not_tested

## Handoff vs live

| Claim | Live |
|-------|------|
| Plugin enabled | **disabled** (`plugins.enabled: []`; probe: `discovered but not enabled`, `disabled via config`) |
| Symlink → repo `integrations/hermes` | verified |
| Middleware allow/deny/exception/garbage | **not re-run** (plugin disabled) |
| Full suite 221 | **not re-run**; `ci_product_suite_record.md` records 201 |
| Wrapper/guard tests 31 | **not re-run**; collect-only now 11 + 11 wrapper/guard, 12 admission = 34 |
| Shadow default / domains | `guard_shadow_mode=True` in `src/aegis/config.py`; `~/.aegis/config.toml` has no `guard_*` keys (defaults) |
| Hermes-agent source | not edited this turn; `package-lock.json` still dirty |
| R-010, R-013, Q-011 open | verified |
| Q-010 / D-014 | historically enable; **currently reverted** by official disable |
| D-016 | still binds; this mission named no model/provider |

## Probe

`PYTHONPATH=src ~/.hermes/hermes-agent/venv/bin/python scripts/probe_hermes_runtime.py` → exit 2, `ok=false`, `error=aegis-gate discovered but not enabled`.

No control/treatment pair. No token conclusion. Production domains unchanged. Shadow/thresholds not changed. `~/.hermes` not modified.

---

# Continuity addendum — 2026-08-15 R-012 live + Q-008 + telemetry

status: verified for live middleware gate; token pair not run; daemon contract landed
artifact: `integrations/hermes` + `src/aegis/wrappers/hermes_telemetry.py` + `src/aegis/daemon_control.py`
action: enable plugin; prove allow+deny; add token-pair recorder; harden daemon startup
timestamp: 2026-08-15T19:05:00-06:00
token_delta: null
savings_percent: null
efficiency_result: not_tested
plugin: enabled
shadow_mode: on
production_guard_allowed_domains: unchanged

## Verified

- `hermes plugins enable aegis-gate --no-allow-tool-override` → `enabled user 1.0.0 aegis-gate`.
- Probe (`~/.hermes/hermes-agent/venv/bin/python scripts/probe_hermes_runtime.py`) ok=true:
  - allow `read_file` next_call=true 4.326ms
  - deny `launch_missiles` blocked_by=aegis next_call=false 1.959ms
  - raising middleware still deny; garbage did not raise
- Telemetry module records measured usage only. Invalid pairs write `token_delta=null`, `savings_percent=null`.
- Daemon: `probe_bind`, `wait_for_health` states, refuse dual-spawn, bind-fail exit 1.
- Full suite: `python3 -m pytest -q` → 243 passed, 1 skipped.
- Production router still healthy: launchd pid 949, `http://127.0.0.1:8787/healthz` reachable.
- Canonical register filled as an index (was empty).

## Not tested / not claimed

- Hermes Desktop / `hermes chat` LLM tool call.
- Any savings percentage.
- D-016 still binds: no matched pair until a named compatible model.

## Next

1. User names model+provider that emits native Hermes `tool_calls`.
2. Run admission gate, then exactly one `scripts/r012_matched_pair.py`.
3. Do not disable shadow. Do not publish `savings_percent`.
4. Q-011 stays closed until D-011 is lifted.

---

# Continuity addendum — 2026-08-15 R-012 admission STOP

status: admission_failed; pair not started
artifact: `/tmp/aegis-r012-measure/admission-20260815.json`
action: one ungated oneshot; score `admit_run`; stop
timestamp: 2026-08-15
model: deepseek/deepseek-v4-flash-0731
provider: nous
session_id: 20260815_131229_2058c8
token_delta: null
savings_percent: null
efficiency_result: not_tested
plugin: enabled
shadow_mode: on
production_guard_allowed_domains: unchanged

## Verified

- Context 1048576 ≥ 64000. Hermes accepted the model.
- Usage present: 1463 in / 76 out / 1795 total / 1 API call. Tokens are not a savings result.
- `tool_call_count=0`. `read_file` did not execute. Marker not returned.
- Stdout was DSML imitation (`invoke name="read_file"`). `no_text_imitation_tool_call=false`.
- `admit_run` admitted=false. Matched pair **not** run.
- Plugin restored: `enabled user 1.0.0 aegis-gate`. Shadow/thresholds/domains unchanged.

## Next

Do not hunt. Await a different named model+provider that emits OpenAI-native Hermes `tool_calls`. Q-011 stays closed.

---

# Continuity addendum — 2026-08-15 false-positive pair request

status: refused; admission still failed
action: do not run matched pair; make admission CLI fail-closed
evidence: `/tmp/aegis-r012-measure/admission-20260815.json` admitted=false; `~/.aegis` writable here; no-arg `r012_admission_gate.py` was a no-op (now exits 2); sandboxed pair leftover `ungated-usage.json` has null tokens and `failed=true` on `~/.hermes/logs/agent.log`
timestamp: 2026-08-15
token_delta: null
savings_percent: null
pair_run: false
plugin: enabled
shadow_mode: on

---

# Continuity addendum — 2026-08-15 D-019 park measurement

status: decided
action: Option B — close R-012 at gate/admission; park R-014 and Q-012
timestamp: 2026-08-15
token_delta: null
savings_percent: null
efficiency_result: parked
plugin: enabled
shadow_mode: on
hermes_config_changed: false

## Decided

- R-012 complete criterion is live allow+deny + fail-closed admission. Not a savings percentage.
- R-014 parked until the user authorizes adding a native-tool-call model+provider.
- Q-012 parked. No configured qualifying model. Do not probe Nous leftovers or Ollama 7B.
- D-015/D-016 still bind any future pair. Q-011 stays closed.

## Next

No measurement work. Option A only if the user names a model+provider and authorizes the Hermes config/billing change.

---

# Continuity addendum — 2026-08-15 D-020 Hermes org catalog

status: verified
action: catalog Hermes organization tools; reclassify memory as write
evidence: `tests/test_hermes_wrapper.py` 12 passed
timestamp: 2026-08-15
shadow_mode: on
production_guard_allowed_domains: unchanged
savings_percent: null

## Verified

- `session_search` / `project_list` allow when scoped; deny when domains empty.
- `memory` decision=allow, capability=`memory.write`, risk=medium (not read).
- `skill_manage` is `skill.write` medium.
- Unknown tools still deny. No Hermes-agent source edit. No billing/model change.

## Residual

R-015: memory persists to Hermes store, not `guard_allowed_domains`.

---

# Continuity addendum — 2026-08-15 D-021 daemon harden

status: verified
action: health classification, bindError recovery, concurrent live probe
evidence: pytest 248 passed, 1 skipped; live :8787 24/24 /healthz; plugin still enabled
timestamp: 2026-08-15
shadow_mode: on
production_launchd_restarted: false
savings_percent: null

## Verified

- `wait_for_health` prefers `bind_failed` over `dead` when `bindError` is present.
- Stale-PID cleanup no longer drops bindError.
- Unhealthy leftover spawn is reaped (`respect_launchd=False` on the Popen path only).
- In-process 16 concurrent /healthz + live launchd 24/24.
- Plugin `aegis-gate` still enabled. Hermes-agent source not edited.

## Not done

- Did not restart production launchd (KeepAlive already running and healthy).

---

# Continuity addendum — 2026-08-15 D-023 note/project skills

status: verified
action: four-skill JSON surface + living MUL corpus in AGIS vault
evidence: focused 37 passed; full suite 274 passed; `tests/test_hermes_memory_utility_labs.py`
timestamp: 2026-08-15
shadow_mode: on
production_guard_allowed_domains: unchanged
savings_percent: null

## Verified

- Records, bounded resolver, four skills, YAML list tags.
- Created `AEGIS/05-Memory-Utility-Labs` (section did not exist). 6 notes discovered by `build_graph`.
- `/Users/ektar/workspace` still 0 notes. R-015 unchanged. No live model probe.

## Next

Use `--root` at MUL for real queries. D-024 search already exists.

---

# Continuity addendum — 2026-08-15 D-025 sprint ledger

status: verified
action: sprint CLI + version 1.1.1 align + `aegis hermes search|resolve`
artifact: `src/aegis/sprints.py` + `05_SPRINT_BOARD.md`
timestamp: 2026-08-15
shadow_mode: on
production_guard_allowed_domains: unchanged
savings_percent: null

## Verified

- `aegis sprint seed|list|start|complete|report|board` writes `~/.aegis/sprints.jsonl`.
- Parked/blocked catalog (SP-010..SP-014) cannot start or complete.
- Product version surfaces are 1.1.1 except Hermes plugin identity 1.0.0.
- `aegis hermes search|resolve` is read-only over existing indexes.

## Not done

- SP-010..SP-014 remain parked/blocked. No pair, encoder, capsule pack_id, or memory-scope change.

---

# Continuity addendum — 2026-08-27 SP-026 sprint ledger reconciliation

status: verified
action: SP-023/024/025 identity correction + setup.py 1.3.1 + `aegis sprint reconcile` CLI
artifact: `src/aegis/sprints.py`, `src/aegis/cli.py`, `tests/test_sprints.py`, `05_SPRINT_BOARD.md`, `01_CANONICAL_REGISTER.md`, `setup.py`
timestamp: 2026-08-27
shadow_mode: on (D-011 unchanged)
production_guard_allowed_domains: unchanged
savings_percent: null (admitted=False)

## Verified (Evidence Verifier run 2026-08-27)

- `python3 -m pytest tests/test_sprints.py -q` → 8 passed
- `python3 -m pytest -q` → 444 passed
- `python3 -m aegis --version` → 1.3.1
- `python3 -m aegis doctor` → v1.3.1 ready
- `python3 -m aegis sprint report` → SP-023 Covering reuse, SP-024 Agency modes, SP-025 Ether retirement
- Live `~/.aegis/sprints.jsonl` reconciled; audit at `~/.aegis/sprint_reconciliations.jsonl`
- `reconcile_known_history()` idempotent — refuses when SP-024/025 exist
- `aegis sprint reconcile` CLI wired

## Budget / reuse (measured, not claimed)

- Reserve: hard_stop (~35% remaining)
- Reuse: 8.9% hit rate (target ≥50%, first milestone 20%)
- Operate E-001 + R-001: pack-first, reuse=hit, land outputs; no parallel agents or new modules

## Not done

- SP-010/011/012/014 remain parked/blocked (Marc approval required for thaw/auth)
- Encoder, implement-pack routing, agent fan-out — deferred
- Reserve recovery — outcome to measure weekly, not a coding sprint

