**A Memory Utility Publication · Memory Utility Labs / Calgary, Alberta**

Formatted volume: [Introducing AEGIS Volume II (PDF)](book/Introducing-AEGIS-vol2.pdf) — 9×6 landscape. Rebuild: `python3 docs/book/build_vol2.py`. Volume I remains [Draft 2](book/Introducing-AEGIS-draft2.pdf).

# Introducing AEGIS — Volume II

System architecture. Issue 1 · 2026 · Product 1.2.0.

Volume I stated the law. This volume states the machinery: control plane, token capacity basin, guard middleware, Hermes routing. Four plates. Four systems. Where a number is not proven, the number stays null. Product routing stays off.

## I. Control plane

Kernel (process / memory / drivers / syscalls). Portable data plane under `~/.aegis/`. Frozen `/v1` API. Honest yield proof.

`aegis os init` lays the plane. `aegis doctor --product` scores it. `aegis os ready` is the floor. Optional: `aegis serve` at `http://127.0.0.1:8787` for OpenAI-compatible calls with `body.aegis.pipeline=true`. The serve daemon is not a host kernel. Agent-kernel scores are not Darwin scores.

The plane is local. Hosted SaaS, consumer marketplace, and host-kernel replacement are out of scope.

## II. Token capacity basin

Tokens are water. They are not free. Pack and scrub before discharge. A reserve is a low-flow state, not an empty one.

Weekly cap: 1 000 000 processed tokens. Reserve floor: 80%. OPEN / THROTTLE / HARD STOP.

Naive: dump -> overflow -> re-read.
Aegis: pack + reserve + implement-full + land + audit.

The work-system is one basin. Chat windows are jurisdictions, not units. Covering reuse hits if hashes still match. After you edit, the cache misses on purpose.

## III. Guard middleware

Single path:

```text
request -> normalize -> ids -> classify -> policy
-> fail-closed -> allow | deny | require-review
-> execute only if permitted -> GuardDecision audit
```

Unknown tools deny. Malformed requests deny. Out-of-scope requests deny. Shadow mode defaults on: the decision is logged, the block is not yet the law. Turn shadow off when the catalog is trusted.

Ledger: `~/.aegis/guard_log.jsonl`. Rotate: `aegis guard rotate`. Hermes wrapper never raises to block a tool; it returns a structured deny payload instead. Hermes middleware itself is fail-open on raise. This module must not be.

## IV. Hermes routing

`aegis hermes search|resolve` is a thin read-only CLI over the local index. Track first. Perplexity only for a live external miss. Perplexity never edits.

Coordination pathways are drawn. Product routing is not authorized. `routing_authorized` stays false. Honesty yield prints measured ledger and billed-pair numbers; `savings_percent` stays null. Advertised tool-call metadata is not admission. A research note is not a routing trial.

The index is a marshal. It is not a switch.

---

*Aegis 1.2.0 — see [FIELD.md](FIELD.md) · [FIRST_RELEASE.md](FIRST_RELEASE.md) · [ABSOLUTE.md](ABSOLUTE.md). Plates: NASA/GSFC 1970s technical poster language. Volume I: geodesic laboratory.*
