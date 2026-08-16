---
title: Semantic Packet Field Contract
type: architecture-note
status: proposed
approval: none
approval_requires: docs/SEMANTIC_PACKET_FIELD_CONTRACT.md
source: Cursor 2026-08-15 field-contract draft
created: 2026-08-15
updated: 2026-08-15
project: aegis
tags:
  - aegis
  - q-013
  - field-contract
---
# Semantic Packet Field Contract

**Status:** proposed. Not approved. Q-013 remains `locked-observe`.

`HermesWrapper` is the only execution gate.

## Six field decisions

- **Mint `pkt_<uuid4>`** at admission. Never copy `request_id` / `trace_id` / `event_id` / `tool_call_id`.
- **Use `parent_id`** as the sole parent. Root intent `null`. Drop `provenance.parent`. Note hops are not parents.
- **Default** `confidence=unknown`, `priority=normal`, `retry_count=0`, maximum 2 then `dead_letter`.
- **Keep sensitivity** separate from redaction. Default `internal`. Redaction does not mean `secret`.
- **Cite `run_id`** without merging it into `GateResult`.
- **Bind `token_budget`** to characters until D-016. Never label chars as tokens. Keep `cost_estimate` null.

## Boundary

No encoder, catalog field, packet emission, router, second gate, D-025, AGIS/05, or `memory.write`.

```mermaid
flowchart TD
    A[Candidate JSON or invoke envelope]
    B[HermesWrapper: sole execution gate]
    H[Q-013 field contract approval]
    C[Deterministic validator]
    D[Packet router]
    E[Encoder]
    F[Catalog fields]
    G[Packet emission]
    X[Reject and audit]

    A --> B
    B --> H
    H -->|Not approved| B
    H -->|Explicit approval of named contract| C
    C -->|Invalid or incomplete| X
    C -->|Valid contract and provenance| D
    D --> E
    E --> F
    F --> G

    classDef gate fill:#4a2c6b,stroke:#c9a0ff,color:#fff
    classDef blocked fill:#5a2a2a,stroke:#ffaaaa,color:#fff
    classDef future fill:#2c4a3b,stroke:#a0ffc9,color:#fff

    class B gate
    class H blocked
    class C,D,E,F,G future
```

Current edge: **Not approved → B**. C–G stay unauthorized until a later execute brief.

## Rejected

Reuse `request_id` as `packet_id`. Dual parent fields. Infer `confidence=high`. Treat `[REDACTED]` as `secret`. Add `run_id` to `GateResult`. Call chars tokens.

## Unresolved (block encoder only)

`provenance.citations` shape. `source` enum. Conceptual admission mint. Q-013 status after approval vs execute brief.

## Approval

Not executed. Copy verbatim:

```text
I approve docs/SEMANTIC_PACKET_FIELD_CONTRACT.md as the Q-013 field contract.
This accepts the six field decisions only.
It does not authorize an encoder, router, catalog field, packet emission, D-025, or a second gate.
HermesWrapper remains the only execution gate.
```
