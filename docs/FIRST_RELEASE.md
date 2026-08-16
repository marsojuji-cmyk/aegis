# First Release Contract

**Status:** internal alpha. Not a release candidate.  
**Boundary:** **B** — token-economy operating layer plus read-only AGIS/Hermes lexical search and bounded context resolution with provenance.  
**Published:** 2026-08-15. Product version **1.1.1** (`pyproject.toml`, `src/aegis/__init__.py`, `setup.py`, CLI `--version`, `README.md`). `integrations/hermes/plugin.yaml` stays **1.0.0** (plugin identity, not product version).

This file is the v1 product boundary. Later install, API, docs, and acceptance work obey it.

## Identity

**Name:** AGIS/Aegis  
**What it is:** a local operator product for the owner of this machine, using Cursor, Hermes, and `~/.aegis/`.  
**What it is not:** a marketplace product, hosted service, second-machine installer, or general consumer application.

**Problem:** wasted context and unproven spend. The product packs, reuses, meters, gates, and retrieves with receipts — it does not grow autonomy or claim model savings.

**Operator:** the owner of this host. Single-user. Local-first.

## Minimum successful workflow

1. Prepare or reuse a context pack.
2. Apply budget and reserve policy.
3. Land output through the output store.
4. Start or checkpoint continuity.
5. Route Hermes actions through `aegis-gate`.
6. Search the canonical AGIS MUL corpus lexically.
7. Resolve bounded graph context.
8. Emit a receipt naming mode, root, pack reuse, budget signal, and gate result.

## In scope

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

## Exclusions (v1)

1. Embeddings and semantic search
2. Embedding-target resolution (unresolved wikilinks stay unresolved)
3. Semantic packets and swarm runtime
4. Graph expansion beyond the existing 9-note AGIS MUL corpus
5. `memory.write` as Aegis memory
6. Auto-invest
7. Auto-tick
8. Parallel fan-out while reserve signal is `throttle`
9. D-025
10. `savings_percent` claims (ledger “saved” tokens are local counterfactual only)
11. Hosted / cloud processing
12. Marketplace packaging
13. Multi-user operation
14. Unbounded autonomous actions
15. Changes to shadow, thresholds, domains, billing, or models
16. Writes to the complementary Documents Labs vault
17. ~~Capsule `artifacts` pack-id lookup~~ — shipped D-026 (`kind=pack` on continuity start)

## Canonical paths

| Role | Path | SoT? |
|---|---|---|
| Hermes living corpus | `/Users/a100/Library/Mobile Documents/iCloud~md~obsidian/Documents/AGIS/AEGIS/05-Memory-Utility-Labs` | Yes — Hermes retrieval |
| Complementary ledger | `/Users/a100/Documents/Memory Utility Labs` | No — not Hermes product SoT |
| Default empty root | `/Users/ektar/workspace` | Valid empty default; not product data |
| Product registers / code | `~/Projects/aegis` | Yes — decisions, risks, questions, this contract |
| Operational data | `~/.aegis/` (or `$AEGIS_HOME`) | Yes — packs, ledger, indexes, outputs |

Do not treat Documents Labs or the empty default root as Hermes product data.

## Safety and privacy

- Hermes retrieval is read-only: it does not mutate notes or indexes.
- No hidden model, network, embedding, or rebuild calls in the v1 workflow.
- Canonical roots must stay explicit and distinguishable.
- `AEGIS_HOME` isolates operational data. Do not write product state into `$HOME` root or vaults.
- `throttle`: invest frozen; reuse and observation allowed.
- Doctrine blocks parallel agents under `throttle`. Code aborts the router only at `hard_stop`. That distinction is documented, not a defect.
- Existing gate behavior is unchanged (shadow default on; live allow/deny as already bound).
- Secrets stay out of memory, registers, and this contract.

## Release classification

**Internal alpha.** Operational on this host. Not product-ready.

Release-candidate transition needs separate evidence for: clean install and doctor; canonical-root / path isolation; restart and recovery; stable API schemas and errors; read-only retrieval; gate enforcement; throttle enforcement; operator receipts; backup/restore and uninstall documentation.

## Known limitations

- Product version identifiers are 1.1.1. Hermes plugin identity remains 1.0.0.
- Continuity start writes `pack_id` into capsule `artifacts`. Empty packs fail closed.
- Doctor classifies Hermes/AGIS roots (`hermes_corpus`). Empty-default or Documents Labs notes indexes fail the check; a missing index is labeled, not treated as product-ready. v1 pin is `hermes_notes_root` or `AEGIS_HERMES_NOTES_ROOT` (package default empty). `DEFAULT_ROOT` is never the v1 pin. Unset pin may still classify this-host AGIS notes as canonical with `v1_ready=no`. `note_graph` rebuild allows only that pin or the FIRST_RELEASE AGIS fallback; Labs, empty default, and arbitrary roots are `PATH_NOT_ALLOWED`. A new process may load `notes.json`+`graph.json` only when schema, signature, and root match that pin/fallback; `files.json` is never a notes graph.
- `aegis hermes search|resolve` is a thin read-only CLI over existing search/resolve. Hermes skills remain `invoke()` + SKILL.md. Cursor skills (`aegis-pack-first|continuity|sprint|hermes|flow`) install via `aegis cursor --install` into `~/.agents/skills`.
- Persistent retrieval tests bind to the iCloud AGIS path on this machine.
- Pack/ledger savings are local counterfactual (`chars/4`), not `savings_percent`.

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
