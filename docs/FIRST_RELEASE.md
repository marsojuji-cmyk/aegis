# First Release Contract

**Status:** local program (second-machine install). Not hosted. Not a consumer marketplace.  
**Boundary:** **C** — portable agent OS (kernel + `/v1` + init/backup) on top of the 1.1.1 token-economy layer and read-only AGIS/Hermes lexical search.  
**Published:** 2026-08-18. Product version **1.2.0**. `integrations/hermes/plugin.yaml` stays **1.0.0**.

This file is the product boundary. Later install, API, docs, and acceptance work obey it.

## Identity

**Name:** AGIS/Aegis  
**What it is:** a local agent operating system: process table, memory accounting, capability drivers, syscalls, portable `AEGIS_HOME`, frozen HTTP `/v1`, honest yield harness. Optional this-host extras: Cursor, Hermes, AGIS MUL.  
**What it is not:** a host kernel (Darwin/Windows/Linux), a hosted service, or a claimed model-savings product.

**Problem:** wasted context and unproven spend. The product packs, reuses, meters, gates, and retrieves with receipts — it does not grow autonomy or claim `savings_percent` without an admitted pair.

**Operator:** one human per `AEGIS_HOME` (or `$AEGIS_USER` namespace). Local-first. Second machine via `pip install -e .` + `aegis os init`.

## Minimum successful workflow

1. `aegis os init` (portable home + MANIFEST schema 2).
2. Prepare or reuse a context pack (`aegis kernel pack` or `aegis pack`).
3. Apply budget and reserve policy (invest is a kernel syscall; frozen on throttle/hard_stop).
4. Land output through the output store.
5. Start or checkpoint continuity.
6. Route Hermes actions through `aegis-gate` when Hermes is present.
7. Search the canonical AGIS MUL corpus lexically when pinned.
8. Emit a receipt naming mode, root, pack reuse, budget signal, and gate result.
9. `aegis os score` and `aegis yield prove` — yield stays labeled `counterfactual_chars4`.

## In scope

- Agent kernel: process, memory, drivers, syscalls
- Portable home: init / backup / restore / uninstall
- Namespaced users via `AEGIS_USER` when `AEGIS_HOME` unset
- Frozen `/v1` required-key contract (`aegis api spec`)
- Honest yield proof and pack hash-cache benchmark
- Context pack creation and reuse
- Budget, reserve, surplus, throttle, and investment-freeze
- Land / output storage
- Continuity start / checkpoint
- Hermes allow / deny / require-review gate
- Read-only `hermes_notes_search`
- Read-only `hermes_resolve_context`
- AGIS MUL path-aware provenance
- Deterministic lexical retrieval
- Bounded graph context packets
- Operator receipts and current budget decisions
- `AEGIS_HOME` data isolation

## Exclusions (v1.2)

1. Embeddings and semantic search
2. Embedding-target resolution (unresolved wikilinks stay unresolved)
3. Semantic packets and swarm runtime
4. Unbounded MUL graph growth (D-030 named 20-note set only)
5. `memory.write` as Aegis memory
6. Auto-invest
7. Auto-tick
8. Parallel fan-out while reserve signal is `throttle`
9. Encoder (Q-013 locked-observe)
10. `savings_percent` claims (ledger “saved” tokens are local counterfactual only)
11. Hosted / cloud processing
12. Consumer marketplace / SaaS tenancy
13. Host kernel / drivers / process isolation of the machine OS
14. Unbounded autonomous actions
15. Changes to shadow, thresholds, domains, billing, or models
16. Writes to the complementary Documents Labs vault
17. Factory OS MUL overlay as the SKU (Q-014: overlay stays knowledge; program SKU is 1.2 kernel)

## Canonical paths

This-host AGIS/Labs paths remain classification labels. Product init does not require them. Pin retrieval with `AEGIS_HERMES_NOTES_ROOT` or `hermes_notes_root`.

| Role | Path | SoT? |
|---|---|---|
| Hermes living corpus | this-host AGIS MUL (classification only) | Yes — Hermes retrieval when pinned |
| Complementary ledger | Documents Labs | No — not Hermes product SoT |
| Default empty root | `/Users/ektar/workspace` | Valid empty default; not product data |
| Product registers / code | repo root | Yes — decisions, risks, questions, this contract |
| Operational data | `$AEGIS_HOME` or `~/.aegis` or `~/.aegis/users/$AEGIS_USER` | Yes — packs, ledger, kernel, outputs |

Do not treat Documents Labs or the empty default root as Hermes product data.

## Safety and privacy

- Hermes retrieval is read-only: it does not mutate notes or indexes.
- No hidden model, network, embedding, or rebuild calls in the v1 workflow.
- Canonical roots must stay explicit and distinguishable.
- `AEGIS_HOME` isolates operational data. Do not write product state into `$HOME` root or vaults.
- `throttle` / `hard_stop`: invest is a kernel syscall and is frozen.
- Doctrine blocks parallel agents under `throttle`. Code aborts the router only at `hard_stop`. That distinction is documented, not a defect.
- Existing gate behavior is unchanged (shadow default on; live allow/deny as already bound).
- Secrets stay out of memory, registers, and this contract.

## Release classification

**Local program.** `aegis os init` + `aegis doctor --product` is the second-machine floor. Hermes/AGIS retrieval remains optional and this-host pin dependent.

Hosted SaaS, consumer marketplace, and host-kernel replacement are out of scope.

## Known limitations

- Product version identifiers are 1.2.0. Hermes plugin identity remains 1.0.0.
- Continuity start writes `pack_id` into capsule `artifacts`. Empty packs fail closed.
- Doctor classifies Hermes/AGIS roots (`hermes_corpus`) without failing the product floor. v1 pin is `hermes_notes_root` or `AEGIS_HERMES_NOTES_ROOT` (package default empty). `DEFAULT_ROOT` is never the v1 pin.
- `aegis hermes search|resolve` is a thin read-only CLI over existing search/resolve.
- Persistent retrieval tests bind to the iCloud AGIS path on this machine.
- Pack/ledger savings are local counterfactual (`chars/4`), not `savings_percent`.
- Agent-kernel scores are not Darwin/Windows kernel scores.

## Source of truth

| Kind | Where |
|---|---|
| This product boundary | `docs/FIRST_RELEASE.md` (this file) |
| Decisions / risks / questions | `01_CANONICAL_REGISTER.md` and the files it indexes |
| Sprint board | `05_SPRINT_BOARD.md` (human index). Ledger: `~/.aegis/sprints.jsonl` |
| Field doctrine | `docs/FIELD.md`, `docs/ABSOLUTE.md` |
| CLI / runtime | `~/Projects/aegis` (`src/aegis/`) |
| Hermes notes | AGIS `AEGIS/05-Memory-Utility-Labs` only |

If another brief, vault note, or isolated-repo view disagrees with this file, this file wins until a later authorized revision.
