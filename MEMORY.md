# Aegis Project Memory

## Architecture
- Product: pack → budget → land → continuity → aegis-gate → honest ledger.
- Hermes path: normalize → policy → redact → allow|deny|require-review → `~/.aegis/guard_log.jsonl`.
- Token pairs: `hermes_telemetry.record_pair`. `savings_percent` null unless admitted.
- Sprints: `aegis sprint` → `~/.aegis/sprints.jsonl`. Board: `05_SPRINT_BOARD.md`.
- Cursor: pack-first. `reuse=hit` → do not Read packed_paths. Capsule artifacts include pack id.

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
- Last ID: D-028. Shot-caller: this agent on unfrozen work. Operator: Cursor only for Aegis. Freeze list binds. No encoder.
- Pin set: `hermes_notes_root` = AGIS MUL. Shadow on. `v1_ready=yes`. Git `80f179e` matches claimed 1.1.1. Scratch left untracked.

## 2026-08-16
- WP-3 / SP-013 unparked and shipped (D-026).
- Reserve W33 throttle. No invest. Idea `idea_3fd3c23eef` closed with actual=0.
- Operator loop accepted: reuse=hit, consumed unchanged, 8/41 (19.5%).

## Rollback
- Plugin: `hermes plugins disable aegis-gate`
- D-026: revert `cursor_bridge.py` pack-first + `cli.py` continuity pack_id lookup
