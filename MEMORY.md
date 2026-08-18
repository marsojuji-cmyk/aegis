# Aegis Project Memory

## Architecture
- Product 1.2.0 is the agent OS: kernel (process/memory/drivers/syscalls) + portable schema-2 home + frozen `/v1` + yield harness on the 1.1.1 JIT token chain.
- Grok Build = Cloud Pro specialist (`grokbuild_aegis_spec.md` packet). Not a co-IDE.
- Hermes: normalize → policy → redact → allow|deny|require-review → `~/.aegis/guard_log.jsonl`.
- Pairs: `hermes_telemetry.record_pair`. `savings_percent` null unless admitted.
- Sprints: `aegis sprint` → `~/.aegis/sprints.jsonl`. Board: `05_SPRINT_BOARD.md`.
- Cursor pack-first. `reuse=hit` → do not Read packed_paths. Capsules store pack id.

## Standing decisions
- D-011: shadow on. No threshold tune. Q-011 closed.
- D-013/D-017: live `aegis-gate` (`allow_tool_override=false`).
- D-015/D-016: no pair / no `token_delta` until admission + named authorized model.
- D-018/D-021: daemon bind/health; bindError preserved; failed start reaps.
- D-019: R-012 complete at gate/admission only. R-014 and Q-012 parked.
- D-020: Hermes org tools catalogued. `memory` is write. R-015: not domain-scoped.
- D-022–D-024: file index, note graph, unified local search. No external API.
- D-025: Sprint CLI. D-026: capsule pack_id + Cursor pack-first + empty-pack refuse.
- D-027: Four Cursor skills via `aegis cursor --install` → `~/.agents/skills`.
- D-029: Flow. Driver / Cursor+Perplexity car / One track. Skill `aegis-flow`.
- D-030: Named MUL factory OS graph 9→20. Unbounded growth still frozen.
- D-031: 1.2.0 product OS. Overlay ≠ SKU. Default engine product. `doctor --product` is second-machine floor.
- Last ID: D-031. Shot-caller: this agent on unfrozen work. Freeze list binds except named graph set. No encoder.
- Pin set: `hermes_notes_root` = AGIS MUL. Shadow on. Auto commit+push on a verified one-intent unit; announce first. Mixed trees / stop-hook repair are not commit points.

## Rollback
- Plugin: `hermes plugins disable aegis-gate`
- D-026: revert `cursor_bridge.py` pack-first + `cli.py` continuity pack_id lookup
- D-029: remove `aegis-flow` from `CURSOR_SKILL_NAMES` + Flow section in CURSORRULES
- D-030: delete the 11 factory OS notes; revert MUL frontmatter; restore retrieval count 9
- D-031: revert kernel/portable/api_contract/yield_proof + version 1.1.1 + FIRST_RELEASE boundary B
- Cloud Pro overlay: revert packet in `grokbuild_aegis_spec.md` + router OPERATING / CORTEX-DOMAIN
