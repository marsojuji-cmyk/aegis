# Semantic Packet Mapping (observe-only)

Repository evidence copy. Canonical note:

`/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Semantic Packet Mapping.md`

No code. No D-025. `HermesWrapper` remains the only gate.

## Locked decision

Deterministic validator. Candidate JSON is untrusted until closed-enum, required-field, provenance, policy, and independent spend checks pass.

## Required mapping

| Existing source | Packet field | Class |
|---|---|---|
| `invoke` (no `intent`; closest `query`/`note_id`/`title`) | `intent` | **gap** — do not mint intent from a skill call |
| guard `capability` / `tool_name` | `kind` | **reject** copy; catalog may candidate `tool_request` only |
| `ContextResult.provenance` + `corpus.root` | `provenance` | **obs** — hops ≠ packet parents; no `valid` |
| `GuardDecision.run_id` (absent on `GateResult`) | `run_id` | **gap** — not a packet-model field |
| `GateResult.decision` | `status` | **reject** copy; validator-assigned only |
| `max_total_chars` / pair usage / reserve | `token_budget` / `cost_estimate` | **obs**; cost `null` until D-016 |
| raw `tool_name`+`args` | `tool_request` (`action`) | **never** from candidate JSON; **exec** only after wrapper |

## Rejected

Candidate `kind`/`status`/`action`. `GuardDecision.action` as packet action. `invoke.ok` as validated. Inferred savings. `memory.write` as persist. Labs as Hermes `--root`.
