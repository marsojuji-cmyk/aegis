# Aegis Project Memory

## Architecture & Decisions
- **Cost Provenance:** Implemented `cost_verification_report` to ensure every run has valid `cost_status` (`observed`, `verified_zero`) and `cost_source`. The cost provenance pipeline requires a continuous block of 5 audited runs without gaps to be considered `trustworthy_for_routing`.
- **Routing Gate:** Defined in `src/aegis/outcomes.py`. `outcome_report()` now strictly requires:
  - Trustworthy pipeline (`pipeline_trustworthy`)
  - Complete cost data for the trial pairs (`cost_complete`)
  - Strict token spend reduction (`cost_delta > 0`)
  - Non-negative quality (`acceptance_delta >= 0`)
  - Non-negative speed (`time_delta >= 0`)

## Completed Work
- **DG06-DG07:** Built the cost verification pipeline and gating checks.
- **DG08:** Locked the pipeline to require a gapless window (`audited == limit`).
- **DG09:** Enforced the strict cost savings policy on routing eligibility.
- **DG10 (Capstone):** Validated the full policy stack on a real production repair (adding `is_first_class` to `lang.py`). The trial achieved a cost savings but was correctly withheld due to incomplete legacy cost data (`cost_complete = False`) and average time regression across the sample.

## Open Follow-ups
- Run subsequent production work under the tracking tools to naturally replace legacy runs (DG01-DG05) with cost-observed runs, eventually unlocking the routing authorization organically.

## 2026-08-12 — Guard-pilot fold
- Decision: `outcomes.*_pilot` is the only durable matched-pair SoT.
- Folded/deleted: `src/aegis/pilot_runner.py`, `src/aegis/pilot_tools.py`, `tests/test_pilot_runner.py`.
- Guard sequence: `tests/test_guard.py::test_guard_tool_pilot_flow` (tmp_path + `aegis_protect`).
- Kept split: `membership_guard` (weekly reserve) vs `AegisGuard` (per-call).
- Persist: sidecar `~/.aegis/guard_log.jsonl`. Not `ledger.record(kind="guard")`.
- Evidence: pack `26edc935cd6abc164873895a`; pytest guard+outcomes+cli 23 passed.
- Owner: Grok (govern) / GrokBuild (executed) / Hermes (this note).
- Rollback: restore the three deleted files from workspace history.
- Next: no product change. Reserve recovery only.
