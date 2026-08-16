# Continuity Bridge Report

**High-fidelity agency transfer protocol** — privileged final action under Budget-Aware **emergency** band (or on demand).

Not a chat summary. A deterministic handoff so the next intelligence (Grok, OpenAI, Cursor, Antigravity) continues with zero rediscovery tax. Saint John post-planning liaison: bridges to action; do not disband the planning core after the report ([`docs/BASIN.md`](BASIN.md) stone 7).

## Trigger

| Trigger | When |
|---------|------|
| `emergency_band` | Budget-Aware band → emergency (auto if `continuity_auto_on_emergency`) |
| `manual` | `aegis intel continuity` |
| `api` | `GET /v1/aegis/continuity` |
| `force` | `maybe_auto_bridge(force=True)` |

Config:

```toml
continuity_bridge_enabled = true
continuity_auto_on_emergency = true
continuity_include_embeddings = true
```

## Artifacts (`~/.aegis/continuity/`)

| File | Role |
|------|------|
| `continuity_bridge_*.md` | Human + pure-text agent handoff |
| `continuity_bridge_*.json` | Structured sections |
| `embedding_handoff_*.json` | Canonical texts + integrity hash + local vectors |
| `latest.md` / `latest.json` / `latest_embedding_handoff.json` | Stable pointers |

## Report sections

1. **Session Ledger** — completed work, open threads, files, live band/burn  
2. **Precision Resume Protocol** — ordered resume steps + commands  
3. **Session Report Card** — KPIs (throughput, signal, budget efficiency, continuity)  
4. **Token / Attention Allocation Directive** — protect / shed_first / workers  
5. **Weekly Transition Anchor** — material for weekly ROI report  
6. **Future Reflections** — ranking/KPI learning notes  
7. **Cross-AI Next Steps** — snapshot, atomic prompts, tool notes (OpenAI / Cursor / Antigravity / Grok), integrity checklist, failure modes  
8. **Semantic Embedding Handoff Pack** — canonical texts + vectors + retrieval queries  

## Embedding pack

- Model: `aegis-local-hash-v1` (deterministic 64-d local embed; re-embed `canonical_text` with production models if needed)  
- `integrity_hash` = SHA-256 of all canonical texts  
- If hash mismatches → discard vectors, use text Bridge only  

### First retrieval queries

1. Highest-priority open thread + next atomic action  
2. Locked decisions (immutable)  
3. Budget-Aware band + never-shed / allocation  
4. Performance report card implications  
5. Continuity friction to avoid  
6. Weekly boundary material  

## CLI / HTTP

```bash
aegis intel continuity
aegis intel continuity --latest
aegis intel continuity --json
```

```
GET /v1/aegis/continuity
GET /v1/aegis/continuity?latest=1
```

## Invariants

- Continuity bridge is **never-shed** (module catalog + always callable).  
- Auto-fires only on emergency band (or force/manual).  
- Hard 125% burn warning path remains independent.  
- Fan-out: paths appear in tick actions; weekly report can cite latest bridge.  
