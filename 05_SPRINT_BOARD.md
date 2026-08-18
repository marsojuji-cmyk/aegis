# Sprint Board

Product `1.2.0`. Operational SoT: `~/.aegis/sprints.jsonl`.
This file is the human index. Registers remain authoritative for D/R/Q.

| ID | Status | Title | Blocked by | Links |
|---|---|---|---|---|
| SP-011 | blocked | Q-011 require-review hard block | D-011, Q-011 | D-011, Q-011 |
| SP-014 | blocked | R-015 memory domain scope | R-015, D-020 | D-020, R-015 |
| SP-010 | parked | R-014 admitted token pair | D-015, D-016, D-019, Q-012, R-014 | D-015, D-016, D-019, R-014, Q-012 |
| SP-012 | parked | Q-013 semantic packet encoder | Q-013 | Q-013 |
| SP-001 | done | Sprint reporting system | — | D-025, R-013 |
| SP-002 | done | Align product version strings to 1.1.1 | — | — |
| SP-003 | done | Thin aegis hermes search|resolve CLI | — | D-024, D-023 |
| SP-013 | done | Continuity capsule artifacts pack_id | FIRST_RELEASE, WP-3 | — |
| SP-015 | done | Cursor pack-first gate + hit/miss receipt | — | — |
| SP-016 | done | Refuse empty continuity packs | — | — |
| SP-017 | done | Four Cursor skills + install | — | — |
| SP-018 | done | Align git ledger to claimed 1.1.1 | — | — |
| SP-019 | done | Driver/car/track flow + aegis-flow skill | — | — |
| SP-020 | done | Factory OS MUL graph + validation | — | D-030 |
| SP-021 | done | Master Aegis 1.2.0 product OS | — | D-031 |
| SP-022 | done | Close 1.2.0 working tree in one-intent units | — | — |

## Detail

### SP-011 — Q-011 require-review hard block

- status: `blocked`
- goal: When (if ever) high-risk require-review becomes a hard block.
- blocked_by: D-011, Q-011

### SP-014 — R-015 memory domain scope

- status: `blocked`
- goal: Hermes memory.write is not domain-scoped. Needs explicit design authorization.
- blocked_by: R-015, D-020

### SP-010 — R-014 admitted token pair

- status: `parked`
- goal: One admitted gated/ungated pair. savings_percent stays null until D-015 admits both sides.
- blocked_by: D-015, D-016, D-019, Q-012, R-014

### SP-012 — Q-013 semantic packet encoder

- status: `parked`
- goal: Encoder only after field contract is explicitly accepted. Not D-025.
- blocked_by: Q-013

### SP-001 — Sprint reporting system

- status: `done`
- goal: CLI + jsonl ledger + repo board. Track sprints without replacing registers.
- verified: CLI+jsonl+board; parked items refuse start/complete
- evidence: tests/test_sprints.py 17 passed with cli_smoke+v1_compound+hermes_search
- T-1 [done]: sprint module + path
- T-2 [done]: CLI seed/list/start/complete/report/board
- T-3 [done]: tests + register index

### SP-002 — Align product version strings to 1.1.1

- status: `done`
- goal: README, setup.py, and CLI --version match pyproject / __version__. Plugin identity stays 1.0.0.
- verified: product version surfaces are 1.1.1; plugin.yaml stays 1.0.0
- evidence: python3 -m aegis --version
- T-1 [done]: setup.py + argparse --version
- T-2 [done]: README + FIRST_RELEASE note

### SP-003 — Thin aegis hermes search|resolve CLI

- status: `done`
- goal: FIRST_RELEASE in-scope retrieval on the product CLI. Read-only. No new index/API.
- verified: read-only search/resolve on product CLI
- evidence: tests/test_sprints.py::test_hermes_search_cli
- T-1 [done]: hermes search wraps unified_search
- T-2 [done]: hermes resolve wraps resolve_context

### SP-013 — Continuity capsule artifacts pack_id

- status: `done`
- goal: Capsules store pack id in artifacts. Parked by FIRST_RELEASE / WP-3.
- blocked_by: FIRST_RELEASE, WP-3
- verified: continuity start writes kind=pack from ctx meta/pack_id; empty pack exit 2
- evidence: tests/test_continuity.py + 303 passed

### SP-015 — Cursor pack-first gate + hit/miss receipt

- status: `done`
- goal: Reuse last pack on subset paths; reuse=hit|miss on composer block; aegis cursor --gate
- verified: last-pack subset reuse; reuse=hit|miss on composer block; cursor --gate exit 0=reuse
- evidence: tests/test_cursor_bridge.py::test_cursor_pack_first_reuse_and_gate

### SP-016 — Refuse empty continuity packs

- status: `done`
- goal: Missing targets pack same-dir neighbors (cap 3) or fail closed
- verified: missing targets pack <=3 neighbors or EMPTY_PACK fail closed
- evidence: tests/test_cursor_bridge.py + test_continuity_start_refuses_empty_pack

### SP-017 — Four Cursor skills + install

- status: `done`
- goal: pack-first, continuity, sprint, hermes → ~/.agents/skills
- verified: four SKILL.md + --install copy; status lists them
- evidence: tests/test_cursor_bridge.py 10 passed; ~/.agents/skills/aegis-*

### SP-018 — Align git ledger to claimed 1.1.1

- status: `done`
- goal: Commit the product remainder already claimed by doctor/registers. Ignore measurement dumps. No new surface. No freeze thaw.
- verified: HEAD contains claimed 1.1.1 (plugin, hermes_skills, doctor corpus, daemon/guard/router). Scratch excluded.
- evidence: 80f179e
- T-1 [done]: Classify dirty tree vs HEAD
- T-2 [done]: Gitignore generated report dumps
- T-3 [done]: Commit product remainder only (hermes plugin/skills/tests + claimed daemon/doctor/guard)

### SP-019 — Driver/car/track flow + aegis-flow skill

- status: `done`
- goal: Perplexity is research-only. Track first. Fifth Cursor skill. No Perplexity client.
- verified: Skill+CURSORRULES+install; Perplexity never edits.
- evidence: tests/test_cursor_bridge.py + ~/.agents/skills/aegis-flow

### SP-020 — Factory OS MUL graph + validation

- status: `done`
- goal: Named 20-note living corpus and adversarial validation without thawing parked controls.
- verified: 11 factory notes + upgraded 9; unresolved embedding link remains; guard/admission tests preserved.
- evidence: tests/test_hermes_retrieval.py, tests/test_factory_os_validation.py

### SP-021 — Master Aegis 1.2.0 product OS

- status: `done`
- goal: Sellable local program: kernel, portable home, frozen /v1, honest yield, second-machine doctor.
- verified: agent-OS layer scores 10 except yield (8 without admitted pair); doctor --product is the floor.
- evidence: tests/test_master_os.py

### SP-022 — Close 1.2.0 working tree in one-intent units

- status: `done`
- goal: Unit1 D-030 remainder. Unit2 outcomes honesty. Unit3 classify leftover dirty. Then merge to main. No freeze thaw. No new surface.
- verified: Unit1 D-030 evidence in git. Unit2 outcomes honesty. Unit3 classified leftover; M-* not scooped. Merge to main next.
- evidence: 444e82e + 796e582
- T-1 [done]: Land D-030 remainder (frontmatter + factory OS validation test)
- T-2 [done]: Land outcomes honesty (untrusted cost_source)
- T-3 [done]: Classify leftover dirty files; keep or drop
