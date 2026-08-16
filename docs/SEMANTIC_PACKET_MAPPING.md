---
title: Semantic Packet Mapping
type: architecture-note
status: locked-observe
source: Cursor brief 2026-08-15 preserve Q-013 locked-observe
created: 2026-08-15
updated: 2026-08-15
project: aegis
tags:
  - aegis
  - semantic-swarm
  - q-013
---
# Semantic Packet Mapping (observe-only)

Q-013 **locked-observe**. No encoder. No router. No D-025. `HermesWrapper` remains the only gate.

Canonical vault note: `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Semantic Packet Mapping.md`  
Status twin: `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Q-013 Locked-Observe Status.md`

This file is the repository evidence copy. The aegis repo has **no** `.gitattributes`. A view that only lists `.gitattributes` is a different project root.

## Locked contract

Candidate JSON is untrusted until:

1. closed-enum validation
2. required-field validation
3. provenance validation
4. policy validation
5. independent spend validation

## Required mapping

| Existing source | Packet field | Class |
|---|---|---|
| `invoke` (no `intent`; closest `query`/`note_id`/`title`) | `intent` | **gap** — do not mint intent from a skill call |
| guard `capability` / `tool_name` | `kind` | **reject** copy; catalog may candidate `tool_request` only |
| `ContextResult.provenance` + `corpus.root` | `provenance` | **obs** — hops ≠ packet parents; no `valid` |
| `GuardDecision.run_id` (absent on `GateResult`) | `run_id` | **gap** — not a packet-model field; keep two ID planes |
| `GateResult.decision` | `status` | **reject** copy; validator-assigned only |
| `max_total_chars` / pair usage / reserve | `token_budget` / `cost_estimate` | **obs**; chars ≠ tokens; cost `null` until D-016 |
| raw `tool_name`+`args` | `tool_request` (`action`) | **never** from candidate JSON; **exec** only after wrapper |

## Constraints

- `invoke.ok` is not `validated`.
- `GuardDecision.action` is audit `allow`/`block`, not packet action.
- `memory.write` is not persist.

## Encoder-blocking gaps

`packet_id`, `parent_id`, `confidence`, `priority`, `retry_count`, `sensitivity` label, `provenance.valid`/`source_time`, `source` enum, ID-plane collapse, token-unit (chars vs tokens).

## Field-contract brief

Proposed, not approved: `docs/SEMANTIC_PACKET_FIELD_CONTRACT.md`. Q-013 stays locked-observe until that file is explicitly accepted. No catalog fields and no packet emit until then.

See `docs/SEMANTIC_PACKET_FIELD_CONTRACT.md` for the blocked-governance flowchart. Current edge: not approved → HermesWrapper.

## Links

- Vault: [[Aegis - Semantic Packet Mapping]]
- Vault: [[Aegis - Q-013 Locked-Observe Status]]
- Vault: [[Aegis - Policy Transmitter and Governance]]
- Repo: `docs/SEMANTIC_PACKET_FIELD_CONTRACT.md`
- Repo: `docs/SEMANTIC_SWARM_VERIFICATION.md`
