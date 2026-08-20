# AEGIS Cursor Handoff — 2026-08-15 (D-019)

You are continuing AEGIS, the authority layer. Hermes is the reasoning layer. Enforce: normalize → policy → redact → allow|deny|require-review → execute only if allowed → audit log.

Repo: `/Users/a100/Projects/aegis`

## Live state

- Plugin **enabled** (`aegis-gate`, `allow_tool_override=false`).
- Live middleware: `read_file` allowed; `launch_missiles` blocked.
- Admission framework fail-closed. Silent/no-arg script is **not** a pass.
- Shadow mode **on**. Thresholds and production domains unchanged.
- Router daemon healthy (launchd `:8787`).
- **R-012 complete at gate/admission only (D-019).**
- **R-014 parked.** `savings_percent` is null. No admitted pair.
- **Q-012 parked.** No configured native-tool-call model.
- **D-020:** Org tools catalogued (`session_search`, `todo`, skills, projects). `memory` is `memory.write`. R-015 residual: Hermes memory store is not domain-scoped.
- **D-021:** Daemon health/bindError/reap hardened. Live :8787 24/24 concurrent /healthz. Production launchd not restarted.
- **D-022:** File indexer landed. Brief: `HERMES_ORG_LAYER_BRIEF.md`. `/Users/ektar/workspace` has 0 indexable files.
- **D-023:** Four skills + living MUL corpus at AGIS `AEGIS/05-Memory-Utility-Labs`. Rebuild: `python3 scripts/hermes_org_skills.py note_graph --action rebuild --root "<MUL>"`. Empty `/Users/ektar/workspace` still valid.
- **D-024:** Unified local search. `python3 scripts/hermes_search.py "query"`. Empty indexes → 0 hits.

## Do next

Nothing on measurement until the user names **and authorizes** a new model+provider (Option A). Then: score `scripts/r012_admission_gate.py <artifact.json>` (exit 2 = stop) → one `scripts/r012_matched_pair.py` only if admitted.

## Do not

- Hunt models or edit Hermes config/billing without explicit authorization.
- Probe Nous leftovers or local 7B Ollama.
- Infer savings from timings or cache_read.
- Disable shadow. Do not lift Q-011.
- Treat no-output admission as success.

## Key IDs

D-011 shadow · D-013 gate · D-015 admission · D-016 no pair until named+authorized model · D-017 live enable · D-018 daemon · D-019 park measurement · R-012 complete-at-gate · R-014 parked · Q-008 answered · Q-011 blocked · Q-012 parked
