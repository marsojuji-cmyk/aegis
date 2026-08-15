# Semantic Swarm Verification

verified_at: 2026-08-15T15:20:08-06:00

Repository evidence copy. Canonical source is the **Documents Labs vault**, not this repo.

Vault twin: `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Semantic Swarm Verification.md`

## Verdict

| Criterion | Result |
|---|---|
| Five notes at claimed `Memory Utility Labs/Aegis - *.md` | **FAIL** (absent at Labs root, AGIS/05, AGIS `Memory Utility Labs/`) |
| Five notes at canonical Architecture paths | **PASS** |
| Valid YAML frontmatter | **PASS** |
| Meaningful content | **PASS** |
| Each links ≥2 cluster peers | **PASS** |
| Policy Transmitter links the other four | **PASS** |
| Parser marked proposed | **PASS** |
| Parser/packets have no execution authority | **PASS** |
| Notes copied into AGIS/05 or this repo | **not done** (D-023 / DEC-OBS-007) |

AGIS iCloud project-file view seeing only PDFs is expected: the swarm cluster is not in that vault.

## Canonical paths and hashes

SHA-256 of full file bytes (UTF-8).

| Note | Absolute path | sha256 | bytes | mtime |
|---|---|---|---|---|
| Thesis | `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Semantic Swarm Thesis.md` | `6b771b3d42810c614e29505f1bb7a90956cef0537cc7abbeeea1b67f28139996` | 5935 | 2026-08-15T15:19:58-06:00 |
| Packet Model | `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Semantic Packet Model.md` | `7381648a735443d6b2de85afe48844f381655a860807561336e32df4da2e5c99` | 5400 | 2026-08-15T15:19:58-06:00 |
| Intent Graph | `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Intent Graph and Assembly Plan.md` | `851fccca7e0eb859e1d601e72f701aee485734da584fa9acffddf69408e38e30` | 4106 | 2026-08-15T15:19:58-06:00 |
| Policy Transmitter | `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Policy Transmitter and Governance.md` | `e1bf3131610e03bf88603bfe7209856ada494a461855e134be571f3b3df13889` | 4255 | 2026-08-15T15:19:55-06:00 |
| Observability | `/Users/a100/Documents/Memory Utility Labs/08-Research/Architecture/Aegis - Observability and Token Economics.md` | `8c61d3cad2ee689c77c25c8c6c35b2dfe3e4b00952a68b31ae50f8bae79df618` | 4056 | 2026-08-15T15:20:00-06:00 |

## Link graph

```text
Policy Transmitter → Thesis, Packet Model, Intent Graph, Observability
Thesis → Packet Model, Intent Graph, Policy, Observability
Packet Model → Thesis, Intent Graph, Observability, Policy
Intent Graph → Thesis, Packet Model, Policy, Observability
Observability → Thesis, Packet Model, Intent Graph, Policy
```

## Parser (proposed)

```text
deterministic structured-output parser
→ strict schema validation
→ Aegis policy/governance validation
→ execution authorization
```

An LLM may assist interpretation. It must not create executable actions or bypass Aegis validation. Packets have no execution authority. `HermesWrapper` remains the only execution gate. Not D-025. See Q-013.

## Why the claimed paths fail

DEC-OBS-007 / D-023: Hermes living corpus is AGIS `AEGIS/05-Memory-Utility-Labs`. Documents Labs is the complementary research ledger. Swarm notes belong under Labs `08-Research/Architecture/`. Bulk-copy into AGIS or vault root is refused.
