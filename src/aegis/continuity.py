"""
Continuity Bridge Report — high-fidelity agency transfer protocol.

Privileged final action when Budget-Aware enters emergency (or on demand).
Produces a self-contained handoff for the same Grok instance, OpenAI, Cursor,
Antigravity, or any competent agent — with optional Semantic Embedding Pack.

Sections:
  1. Session Ledger
  2. Precision Resume Protocol
  3. Session Report Card
  4. Token / Attention Allocation Directive
  5. Weekly Transition Anchor
  6. Future Reflections & Learning Capture
  7. Cross-AI Next Steps & Handoff Packet
  8. Semantic Embedding Handoff Pack
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis import __version__
from aegis.config import AegisConfig, load_config, opt_in
from aegis.paths import continuity_dir, continuity_events_path, ensure_home

_LOCK = threading.RLock()
HANDOFF_VERSION = "1.0"
BRIDGE_KIND = "continuity_bridge"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


def _sha256_texts(texts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\n---\n")
    return h.hexdigest()


def _local_embed(text: str, dims: int = 64) -> List[float]:
    """
    Deterministic lightweight embedding (no external API).
    Stable for identical canonical text; receiving systems may re-embed
    with text-embedding-3-large / voyage / nomic using canonical_text.
    """
    # bag of hashed tokens → fixed dims
    vec = [0.0] * dims
    tokens = re.findall(r"[a-z0-9_./-]{2,}", (text or "").lower())
    if not tokens:
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(dims):
            # signed byte contribution
            b = digest[i % len(digest)]
            vec[i] += (b / 127.5) - 1.0
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def _gather_context(cfg: AegisConfig) -> Dict[str, Any]:
    """Collect live Aegis state for the bridge (best-effort, never raises)."""
    out: Dict[str, Any] = {
        "version": __version__,
        "cfg": {
            "reserve_floor": cfg.reserve_floor,
            "budget_aware_mode": getattr(cfg, "budget_aware_mode", True),
            "burn_warning_multiplier": getattr(cfg, "burn_warning_multiplier", 1.25),
            "auto_tick": opt_in(cfg, "auto_tick"),
            "auto_invest": opt_in(cfg, "auto_invest"),
        },
    }
    try:
        from aegis.usage_intel import analyze_usage

        out["usage"] = analyze_usage()
    except Exception as exc:  # noqa: BLE001
        out["usage"] = {"error": str(exc)}
    try:
        from aegis.forecast import predict_budget

        out["forecast"] = predict_budget(cfg, usage=out.get("usage"))
    except Exception as exc:  # noqa: BLE001
        out["forecast"] = {"error": str(exc)}
    try:
        from aegis.burn import burn_status

        out["burn"] = burn_status(
            cfg,
            usage=out.get("usage"),
            forecast=out.get("forecast"),
            record_events=False,
        )
    except Exception as exc:  # noqa: BLE001
        out["burn"] = {"error": str(exc)}
    try:
        from aegis.budget_aware import evaluate, module_catalog

        out["budget"] = evaluate(cfg, burn=out.get("burn"), dry_run=True)
        out["module_catalog"] = module_catalog()[:12]
    except Exception as exc:  # noqa: BLE001
        out["budget"] = {"error": str(exc)}
    try:
        from aegis.fund import surplus_snapshot

        out["surplus"] = surplus_snapshot(cfg)
    except Exception as exc:  # noqa: BLE001
        out["surplus"] = {"error": str(exc)}
    try:
        from aegis.ideas import list_ideas

        out["ideas"] = list_ideas(status="queued", by_roi=True)[:8]
    except Exception:  # noqa: BLE001
        out["ideas"] = []
    try:
        from aegis.intelligence import load_intel_state

        out["intel_state"] = load_intel_state()
    except Exception:  # noqa: BLE001
        out["intel_state"] = {}
    try:
        from aegis.memory import memory_stats

        out["memory"] = memory_stats()
    except Exception:  # noqa: BLE001
        out["memory"] = {}
    return out


def _kpi_report_card(ctx: Dict[str, Any]) -> Dict[str, Any]:
    usage = ctx.get("usage") or {}
    burn = ctx.get("burn") or {}
    budget = ctx.get("budget") or {}
    surplus = ctx.get("surplus") or {}
    intel = ctx.get("intel_state") or {}
    reduction = float(usage.get("reduction_percent") or 0)
    cache_hit = float(usage.get("cache_hit_rate_percent") or 0)
    rem = float(usage.get("remaining_pct") or burn.get("remaining_pct") or 0)
    ratio_pct = float(burn.get("ratio_pct") or 0)
    ticks = int(intel.get("ticks") or 0)
    # simple 0–100 scores
    throughput = min(100.0, ticks * 5.0 + float(usage.get("transactions") or 0) * 0.5)
    signal = min(100.0, reduction * 0.7 + cache_hit * 0.3)
    budget_eff = max(0.0, min(100.0, 100.0 - max(0.0, ratio_pct - 80.0)))
    continuity = 90.0 if budget.get("band") != "emergency" else 70.0
    leverage = min(100.0, float(surplus.get("available_credits") or 0) / 1000.0 + reduction)
    overall = round((throughput + signal + budget_eff + continuity + leverage) / 5.0, 1)
    return {
        "throughput": round(throughput, 1),
        "signal_density": round(signal, 1),
        "budget_efficiency": round(budget_eff, 1),
        "decision_quality": round(min(100.0, 50.0 + reduction * 0.4), 1),
        "continuity_health": round(continuity, 1),
        "forward_leverage": round(min(100.0, leverage), 1),
        "overall": overall,
        "raw": {
            "ticks": ticks,
            "transactions": usage.get("transactions"),
            "reduction_percent": reduction,
            "cache_hit_rate_percent": cache_hit,
            "burn_ratio_pct": ratio_pct,
            "remaining_pct": rem,
            "band": budget.get("band"),
        },
    }


def _allocation_directive(ctx: Dict[str, Any]) -> Dict[str, Any]:
    budget = ctx.get("budget") or {}
    plan = budget.get("plan") or {}
    never_shed = [
        m["name"]
        for m in (ctx.get("module_catalog") or [])
        if m.get("never_shed")
    ]
    shed_first = list(plan.get("shed") or []) or [
        m["name"]
        for m in (ctx.get("module_catalog") or [])
        if not m.get("never_shed")
    ][-5:]
    return {
        "protect": never_shed or ["surplus_sync", "usage_intel", "forecast", "burn_status", "weekly_report"],
        "shed_first": shed_first,
        "recommended_workers": budget.get("recommended_workers"),
        "source_preference": budget.get("source_preference") or plan.get("source_preference"),
        "band": budget.get("band"),
        "token_priority": [
            "1. Never-shed critical path (usage, forecast, burn, weekly report)",
            "2. Auto-invest only if reserve ok and band ≤ adaptive",
            "3. Cache optimize when band ≤ caution",
            "4. Enrichment / seed ideas last (shed first under emergency)",
        ],
    }


def _locked_decisions(ctx: Dict[str, Any]) -> List[str]:
    cfg = ctx.get("cfg") or {}
    return [
        f"Reserve floor ≥ {float(cfg.get('reserve_floor', 0.8)) * 100:.0f}% (Absolute Form — never lower).",
        f"Burn critical at ≥ {float(cfg.get('burn_warning_multiplier', 1.25)):.0%} of safe daily — cut fan-out.",
        "Budget-Aware Mode is the control loop; fan-out surfaces consume events only (no re-ranking).",
        "Never-shed modules: surplus_sync, usage_intel, forecast, burn_status, weekly_report, continuity_bridge.",
        "Config is single source of truth for all burn/budget thresholds.",
        "Do not re-open settled architecture: progressive bands 80/100/125 + hysteresis.",
    ]


def _atomic_actions(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    band = (ctx.get("budget") or {}).get("band") or "ok"
    actions = [
        {
            "id": "A1",
            "title": "Confirm burn + budget band",
            "prompt": (
                "Run `python3 -m aegis intel burn` and `python3 -m aegis intel budget`. "
                "Report level, ratio_pct, band, modules_shed, recommended_workers. "
                "Do not change config yet."
            ),
        },
        {
            "id": "A2",
            "title": "Load Continuity Bridge artifacts",
            "prompt": (
                "Read the latest files under ~/.aegis/continuity/ "
                "(continuity_bridge_*.md + embedding_handoff_*.json). "
                "Treat locked decisions as immutable. Do not rediscover settled design."
            ),
        },
        {
            "id": "A3",
            "title": "Resume highest-ROI open thread",
            "prompt": (
                "From the Bridge Session Ledger and Atomic Actions, identify the single "
                "highest-priority incomplete thread. Execute only its next atomic step. "
                "Respect Budget-Aware shed list."
            ),
        },
        {
            "id": "A4",
            "title": "Run tests after any code change",
            "prompt": (
                "cd ~/Projects/aegis && python3 -m pytest -q --tb=line. "
                "Fix failures before expanding scope."
            ),
        },
        {
            "id": "A5",
            "title": "Refresh weekly ROI if week boundary",
            "prompt": (
                "python3 -m aegis intel report. Attach Burn health + Budget-Aware sections "
                "to any status update."
            ),
        },
    ]
    if band in ("adaptive", "emergency"):
        actions.insert(
            1,
            {
                "id": "A0",
                "title": "Stay inside budget-aware constraints",
                "prompt": (
                    f"Current band is {band}. Do not re-enable shed modules. "
                    "Prefer cache/reuse/mock sources. Cut fan-out: fewer parallel tasks "
                    "and smaller batches. Only run never-shed critical path until ratio < 100%."
                ),
            },
        )
    return actions


def _build_sections(ctx: Dict[str, Any], session_id: str, trigger: str) -> Dict[str, Any]:
    usage = ctx.get("usage") or {}
    burn = ctx.get("burn") or {}
    budget = ctx.get("budget") or {}
    forecast = ctx.get("forecast") or {}
    surplus = ctx.get("surplus") or {}
    intel = ctx.get("intel_state") or {}
    kpis = _kpi_report_card(ctx)
    alloc = _allocation_directive(ctx)
    locked = _locked_decisions(ctx)
    atomics = _atomic_actions(ctx)
    ideas = ctx.get("ideas") or []

    ledger = {
        "session_id": session_id,
        "generated_at": _now(),
        "trigger": trigger,
        "product_version": ctx.get("version"),
        "completed": [
            "Intelligence Layer v1.1.1 hardened (policy_nudges, atomic IO, idempotent ticks)",
            "Progressive burn bands 80/100/125 with multi-surface fan-out",
            "Budget-Aware Mode: hysteresis SM, ranking, shed/throttle, tick gates",
            "Continuity Bridge + embedding handoff pack (this artifact)",
        ],
        "open_threads": [
            {
                "id": "T1",
                "title": "Learned ROI weights for module ranking",
                "status": "queued",
                "next": "Replace static ModuleSpec scores with measured weekly ROI",
            },
            {
                "id": "T2",
                "title": "Token-weighted top burn consumers",
                "status": "queued",
                "next": "Extend burn.top_consumers beyond count-share",
            },
            {
                "id": "T3",
                "title": "Offline last-known safe_daily path",
                "status": "queued",
                "next": "Cache safe_daily in burn_state for degraded network",
            },
        ],
        "config_snapshot": ctx.get("cfg"),
        "intel_ticks": intel.get("ticks"),
        "last_intel_actions": intel.get("last_actions") or [],
        "files": [
            "~/Projects/aegis/src/aegis/budget_aware.py",
            "~/Projects/aegis/src/aegis/burn.py",
            "~/Projects/aegis/src/aegis/continuity.py",
            "~/Projects/aegis/src/aegis/intelligence.py",
            "~/.aegis/config.toml",
            "~/.aegis/continuity/",
        ],
        "live": {
            "band": budget.get("band"),
            "burn_level": burn.get("level"),
            "ratio_pct": burn.get("ratio_pct"),
            "avg_daily_burn": burn.get("avg_daily_burn"),
            "safe_daily": burn.get("safe_daily"),
            "reserve_signal": surplus.get("reserve_signal") or usage.get("reserve_signal"),
            "remaining_pct": usage.get("remaining_pct") or forecast.get("remaining_pct"),
            "modules_shed": budget.get("modules_shed"),
            "workers": budget.get("recommended_workers"),
        },
    }

    resume = {
        "protocol": "precision_resume_v1",
        "steps": [
            "1. Load this Continuity Bridge (md + json) and embedding_handoff if vector-capable.",
            "2. Run retrieval queries (section 8) OR read Cross-AI Next Steps if pure-text.",
            "3. Verify Handoff Integrity Checklist — abort re-discovery if checks fail.",
            "4. Execute Atomic Actions in order (A0/A1…); one action per turn when budget-tight.",
            "5. Re-run pytest after code edits; do not expand scope until green.",
            "6. On band recovery (ratio under exit hysteresis), restore shed modules via normal tick.",
        ],
        "cwd": "~/Projects/aegis",
        "env": "AEGIS_HOME=~/.aegis PYTHONPATH=src",
        "commands": [
            "python3 -m aegis doctor",
            "python3 -m aegis intel budget",
            "python3 -m aegis intel burn",
            "python3 -m pytest -q --tb=line",
        ],
    }

    cross_ai = {
        "project_state_snapshot": (
            f"Aegis {ctx.get('version')} Intelligence Layer is production-hardened with "
            f"Budget-Aware Mode band={budget.get('band')} "
            f"(burn ratio {burn.get('ratio_pct')}% of safe daily "
            f"{burn.get('safe_daily')} tok). Reserve signal="
            f"{surplus.get('reserve_signal') or usage.get('reserve_signal')}, "
            f"remaining capacity {usage.get('remaining_pct')}%. "
            f"Control loop sheds low-ROI modules under adaptive/emergency while "
            f"never-shed critical path continues. Continuity Bridge is the handoff protocol."
        ),
        "snapshot_bullets": [
            f"Band: {budget.get('band')} · burn level: {burn.get('level')}",
            f"Shed: {', '.join(budget.get('modules_shed') or []) or 'none'}",
            f"Protect: {', '.join(alloc['protect'][:6])}",
            f"Top idea: {(ideas[0].get('title') if ideas else 'none queued')}",
            "Do not re-litigate: 80/100/125 bands, hysteresis, config SSOT",
        ],
        "atomic_actions": atomics,
        "context_pack": {
            "do_not_rediscover": locked,
            "must_load": ledger["files"],
            "budget_ranking": alloc,
            "kpis": kpis,
        },
        "tool_adaptations": {
            "openai": (
                "First message: paste Project State Snapshot + Atomic Action A1 as the only task. "
                "Attach locked decisions as system constraints. Ask model to execute one action, "
                "then stop for verification. Prefer JSON/diff output."
            ),
            "cursor": (
                "Composer/Agent: @-mention src/aegis/budget_aware.py, continuity.py, "
                "intelligence.py, docs/BUDGET_AWARE.md. Prompt: "
                "'Continue Aegis from Continuity Bridge; execute only action A1; "
                "respect never-shed list; run pytest after edits.'"
            ),
            "antigravity": (
                "Entry: load bridge markdown as skill context; set mode=implement; "
                "paths=[budget_aware.py, continuity.py]; task=atomic A1; "
                "use aegis wrap --provider antigravity when routing models."
            ),
            "grok": (
                "Resume with: 'Continue from Continuity Bridge at ~/.aegis/continuity/latest. "
                "Band and shed list are authoritative. Next action: A1.'"
            ),
        },
        "integrity_checklist": [
            "Bridge integrity_hash matches embedding pack (if present)",
            "Band and modules_shed match `aegis intel budget`",
            "Locked decisions still true (reserve floor, never-shed set)",
            "No attempt to re-enable shed modules while band ≥ adaptive",
            "pytest green before new features",
        ],
        "failure_modes_to_avoid": [
            "Re-interpreting settled band thresholds or re-deriving ranking logic in UI",
            "Re-exploring discarded paths (manual-only burn warnings without control loop)",
            "Ignoring budget ranking and launching parallel high-cost fan-out",
            "Summarizing instead of executing the next atomic action",
            "Lowering reserve_floor under pressure",
        ],
    }

    weekly = {
        "week": usage.get("week") or forecast.get("week"),
        "material_for_weekly_report": [
            f"Budget-Aware band period snapshot: {budget.get('band')}",
            f"Burn ratio {burn.get('ratio_pct')}% · safe_daily {burn.get('safe_daily')}",
            f"Modules shed: {budget.get('modules_shed')}",
            f"KPI overall {kpis.get('overall')} · reduction {usage.get('reduction_percent')}%",
            "Continuity Bridge generated — handoff protocol available under ~/.aegis/continuity/",
        ],
        "boundary_state": ledger["live"],
    }

    reflections = [
        "Static module scores work for v1; measure actual savings per module next.",
        "Emergency auto-bridge reduces human drag at rate limits — keep as never-shed action.",
        "Embedding pack should stay text-first; vectors are accelerators not requirements.",
        "False positives on burn ratio need weekly review of safe_daily estimation.",
    ]

    return {
        "session_ledger": ledger,
        "precision_resume": resume,
        "report_card": kpis,
        "allocation_directive": alloc,
        "weekly_anchor": weekly,
        "reflections": reflections,
        "cross_ai": cross_ai,
        "locked_decisions": locked,
    }


def _canonical_blocks(
    sections: Dict[str, Any],
) -> List[Tuple[str, str, str, Dict[str, Any]]]:
    """(id, label, canonical_text, metadata)."""
    ledger = sections["session_ledger"]
    cross = sections["cross_ai"]
    alloc = sections["allocation_directive"]
    kpis = sections["report_card"]
    locked = sections["locked_decisions"]
    atomics = cross["atomic_actions"]

    intent = (
        f"Session intent: Continue Aegis Intelligence Layer under Budget-Aware Mode. "
        f"Trigger={ledger.get('trigger')}. Band={ledger['live'].get('band')}. "
        f"Completed: {'; '.join(ledger['completed'][:3])}. "
        f"Locked: reserve floor and never-shed critical path. "
        f"Next: execute atomic actions without rediscovery."
    )
    threads = []
    for t in ledger.get("open_threads") or []:
        threads.append(
            f"Active thread {t['id']}: {t['title']}. Status={t['status']}. Next={t['next']}."
        )
    decision_text = "Decision anchors (immutable):\n" + "\n".join(f"- {x}" for x in locked)
    ranking_text = (
        f"Priority & ranking state: band={alloc.get('band')}. "
        f"Protect={', '.join(alloc.get('protect') or [])}. "
        f"Shed first={', '.join(alloc.get('shed_first') or [])}. "
        f"Workers={alloc.get('recommended_workers')}. "
        f"Sources={', '.join(alloc.get('source_preference') or [])}."
    )
    perf_text = (
        f"Performance: overall={kpis.get('overall')} throughput={kpis.get('throughput')} "
        f"signal={kpis.get('signal_density')} budget_eff={kpis.get('budget_efficiency')} "
        f"continuity={kpis.get('continuity_health')} leverage={kpis.get('forward_leverage')}. "
        f"Raw={json.dumps(kpis.get('raw') or {}, sort_keys=True)}."
    )
    next_text = "Next atomic actions:\n" + "\n".join(
        f"{a['id']}: {a['title']} :: {a['prompt']}" for a in atomics
    )

    blocks: List[Tuple[str, str, str, Dict[str, Any]]] = [
        ("session_intent", "Session Intent Vector", intent, {"priority": "highest"}),
    ]
    for i, t in enumerate(threads):
        blocks.append(
            (
                f"active_thread_{i+1:02d}",
                f"Active Thread {i+1}",
                t,
                {"thread_status": "open", "never_shed": True},
            )
        )
    blocks.extend(
        [
            ("decision_anchors", "Decision Anchors", decision_text, {"priority": "highest"}),
            ("priority_ranking", "Priority & Ranking State", ranking_text, {"priority": "high"}),
            ("performance_context", "Performance Context", perf_text, {"priority": "medium"}),
            ("next_action", "Next-Action Vector Source", next_text, {"priority": "highest"}),
        ]
    )
    return blocks


def build_embedding_pack(
    sections: Dict[str, Any],
    *,
    session_id: str,
    include_vectors: bool = True,
) -> Dict[str, Any]:
    blocks = _canonical_blocks(sections)
    canonical_texts = [b[2] for b in blocks]
    integrity = _sha256_texts(canonical_texts)
    vectors = []
    for bid, label, text, meta in blocks:
        entry: Dict[str, Any] = {
            "id": bid,
            "label": label,
            "canonical_text": text,
            "metadata": meta,
        }
        if include_vectors:
            entry["vector"] = _local_embed(text, dims=64)
            entry["dimensions"] = 64
        vectors.append(entry)
    return {
        "handoff_version": HANDOFF_VERSION,
        "generated_at": _now(),
        "session_id": session_id,
        "embedding_model": "aegis-local-hash-v1",
        "dimensions": 64 if include_vectors else 0,
        "distance_metric": "cosine",
        "integrity_hash": integrity,
        "note": (
            "Vectors are deterministic local embeddings for offline continuity. "
            "Re-embed canonical_text with text-embedding-3-large / voyage-3 / nomic "
            "for production RAG if desired."
        ),
        "vectors": vectors,
        "retrieval_hints": [
            "What is the single highest-priority open thread right now?",
            "Which decisions are already locked and must not be re-opened?",
            "What is the current Budget-Aware band and ranking posture?",
            "What does the performance report card say about efficiency and signal density?",
            "What is the exact next atomic action the previous session intended?",
            "How cleanly should handoffs avoid re-discovery and fan-out thrash?",
        ],
    }


def render_markdown(bridge: Dict[str, Any]) -> str:
    s = bridge["sections"]
    ledger = s["session_ledger"]
    resume = s["precision_resume"]
    kpis = s["report_card"]
    alloc = s["allocation_directive"]
    weekly = s["weekly_anchor"]
    cross = s["cross_ai"]
    emb = bridge.get("embedding_pack") or {}
    live = ledger.get("live") or {}

    lines = [
        f"# Continuity Bridge Report",
        "",
        f"**handoff_version:** {HANDOFF_VERSION}  ",
        f"**session_id:** `{bridge.get('session_id')}`  ",
        f"**generated_at:** {bridge.get('generated_at')}  ",
        f"**trigger:** {bridge.get('trigger')}  ",
        f"**aegis:** {bridge.get('version')}  ",
        "",
        "High-fidelity agency transfer protocol — not a chat summary.",
        "",
        "---",
        "",
        "## 1. Session Ledger",
        "",
        f"- Week: {weekly.get('week')}",
        f"- Band: **{live.get('band')}** · burn **{live.get('burn_level')}** "
        f"({live.get('ratio_pct')}% of safe)",
        f"- Burn/safe: {live.get('avg_daily_burn')} / {live.get('safe_daily')} tok/day",
        f"- Reserve: {live.get('reserve_signal')} · remaining {live.get('remaining_pct')}%",
        f"- Workers: {live.get('workers')}",
        f"- Intel ticks: {ledger.get('intel_ticks')}",
        "",
        "### Completed",
    ]
    for c in ledger.get("completed") or []:
        lines.append(f"- {c}")
    lines.extend(["", "### Open threads"])
    for t in ledger.get("open_threads") or []:
        lines.append(f"- **{t['id']}** {t['title']} — next: {t['next']}")
    lines.extend(["", "### Files"])
    for f in ledger.get("files") or []:
        lines.append(f"- `{f}`")
    if ledger.get("last_intel_actions"):
        lines.extend(["", "### Recent intel actions"])
        for a in (ledger.get("last_intel_actions") or [])[-12:]:
            lines.append(f"- {a}")

    lines.extend(["", "---", "", "## 2. Precision Resume Protocol", ""])
    for step in resume.get("steps") or []:
        lines.append(f"- {step}")
    lines.extend(["", "### Commands"])
    for cmd in resume.get("commands") or []:
        lines.append(f"- `{cmd}`")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Session Report Card",
            "",
            f"| KPI | Score |",
            f"|-----|------:|",
            f"| Throughput | {kpis.get('throughput')} |",
            f"| Signal density | {kpis.get('signal_density')} |",
            f"| Budget efficiency | {kpis.get('budget_efficiency')} |",
            f"| Decision quality | {kpis.get('decision_quality')} |",
            f"| Continuity health | {kpis.get('continuity_health')} |",
            f"| Forward leverage | {kpis.get('forward_leverage')} |",
            f"| **Overall** | **{kpis.get('overall')}** |",
            "",
            f"Raw: `{json.dumps(kpis.get('raw') or {}, sort_keys=True)}`",
        ]
    )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Token / Attention Allocation Directive",
            "",
            f"- Band: **{alloc.get('band')}**",
            f"- Protect (never-shed): {', '.join(alloc.get('protect') or [])}",
            f"- Shed first: {', '.join(alloc.get('shed_first') or [])}",
            f"- Workers: {alloc.get('recommended_workers')}",
            f"- Sources: {', '.join(alloc.get('source_preference') or [])}",
            "",
            "### Priority order",
        ]
    )
    for p in alloc.get("token_priority") or []:
        lines.append(f"- {p}")

    lines.extend(["", "---", "", "## 5. Weekly Transition Anchor", ""])
    for m in weekly.get("material_for_weekly_report") or []:
        lines.append(f"- {m}")
    lines.append(f"- Boundary state: `{json.dumps(weekly.get('boundary_state') or {}, sort_keys=True)}`")

    lines.extend(["", "---", "", "## 6. Future Reflections & Learning Capture", ""])
    for r in s.get("reflections") or []:
        lines.append(f"- {r}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 7. Cross-AI Next Steps & Handoff Packet",
            "",
            "### Current Project State Snapshot",
            "",
            cross.get("project_state_snapshot") or "",
            "",
        ]
    )
    for b in cross.get("snapshot_bullets") or []:
        lines.append(f"- {b}")
    lines.extend(["", "### Exact Next Atomic Actions", ""])
    for a in cross.get("atomic_actions") or []:
        lines.append(f"#### {a['id']}: {a['title']}")
        lines.append("")
        lines.append("```")
        lines.append(a["prompt"])
        lines.append("```")
        lines.append("")
    lines.extend(["", "### Context Pack (do not rediscover)", ""])
    for d in (cross.get("context_pack") or {}).get("do_not_rediscover") or []:
        lines.append(f"- {d}")
    lines.extend(["", "### Tool-Specific Adaptation Notes", ""])
    for tool, note in (cross.get("tool_adaptations") or {}).items():
        lines.append(f"**{tool}:** {note}")
        lines.append("")
    lines.extend(["", "### Handoff Integrity Checklist", ""])
    for c in cross.get("integrity_checklist") or []:
        lines.append(f"- [ ] {c}")
    lines.extend(["", "### Failure Modes to Avoid", ""])
    for f in cross.get("failure_modes_to_avoid") or []:
        lines.append(f"- {f}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 8. Semantic Embedding Handoff Pack",
            "",
            "**Purpose:** Portable cognitive state for embedding-capable systems "
            "(Cursor RAG, OpenAI vector stores, Antigravity memory, local indexes).",
            "",
            f"- embedding_model: `{emb.get('embedding_model')}`",
            f"- dimensions: {emb.get('dimensions')}",
            f"- distance_metric: {emb.get('distance_metric')}",
            f"- integrity_hash: `{emb.get('integrity_hash')}`",
            f"- pack_file: `{bridge.get('embedding_path')}`",
            "",
            "### Canonical texts (single source of truth)",
            "",
        ]
    )
    for v in emb.get("vectors") or []:
        lines.append(f"#### {v.get('label')} (`{v.get('id')}`)")
        lines.append("")
        lines.append("```")
        lines.append(str(v.get("canonical_text") or "")[:2000])
        lines.append("```")
        lines.append("")
    lines.extend(["### Recommended first retrieval queries", ""])
    for i, q in enumerate(emb.get("retrieval_hints") or [], 1):
        lines.append(f"{i}. {q}")
    lines.extend(
        [
            "",
            "If integrity_hash does not match, discard vectors and use pure text Bridge.",
            "",
            "---",
            "",
            f"_Aegis Continuity Bridge {HANDOFF_VERSION} · privileged emergency handoff_",
            "",
        ]
    )
    return "\n".join(lines)


def _append_event(event: Dict[str, Any]) -> None:
    ensure_home()
    with continuity_events_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def generate_bridge(
    cfg: Optional[AegisConfig] = None,
    *,
    trigger: str = "manual",
    include_embeddings: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Build Continuity Bridge + embedding pack; write under ~/.aegis/continuity/.
    Privileged final action — always allowed (never-shed).
    """
    cfg = cfg or load_config()
    if not getattr(cfg, "continuity_bridge_enabled", True) and trigger != "force":
        return {"ok": False, "error": "continuity_bridge_enabled=false"}

    session_id = _session_id()
    ts = _now().replace(":", "").replace("+00:00", "Z")
    ctx = _gather_context(cfg)
    sections = _build_sections(ctx, session_id, trigger)
    embed_on = (
        include_embeddings
        if include_embeddings is not None
        else bool(getattr(cfg, "continuity_include_embeddings", True))
    )
    embedding_pack = build_embedding_pack(
        sections, session_id=session_id, include_vectors=embed_on
    )

    cdir = continuity_dir()
    ensure_home()
    cdir.mkdir(parents=True, exist_ok=True)
    base = f"continuity_bridge_{ts}_{session_id}"
    json_path = cdir / f"{base}.json"
    md_path = cdir / f"{base}.md"
    emb_path = cdir / f"embedding_handoff_{ts}_{session_id}.json"
    latest_md = cdir / "latest.md"
    latest_json = cdir / "latest.json"
    latest_emb = cdir / "latest_embedding_handoff.json"

    bridge: Dict[str, Any] = {
        "ok": True,
        "kind": BRIDGE_KIND,
        "handoff_version": HANDOFF_VERSION,
        "session_id": session_id,
        "generated_at": _now(),
        "trigger": trigger,
        "version": __version__,
        "sections": sections,
        "embedding_pack": embedding_pack,
        "paths": {},
    }

    with _LOCK:
        emb_path.write_text(json.dumps(embedding_pack, indent=2), encoding="utf-8")
        bridge["embedding_path"] = str(emb_path)
        md = render_markdown(bridge)
        bridge["markdown"] = md
        # store without huge markdown duplicate in json optional — keep paths
        store = {k: v for k, v in bridge.items() if k != "markdown"}
        store["markdown_path"] = str(md_path)
        store["embedding_path"] = str(emb_path)
        json_path.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
        md_path.write_text(md, encoding="utf-8")
        latest_md.write_text(md, encoding="utf-8")
        latest_json.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
        latest_emb.write_text(json.dumps(embedding_pack, indent=2), encoding="utf-8")
        event = {
            "ts": _now(),
            "kind": "continuity_bridge",
            "session_id": session_id,
            "trigger": trigger,
            "band": (ctx.get("budget") or {}).get("band"),
            "markdown_path": str(md_path),
            "json_path": str(json_path),
            "embedding_path": str(emb_path),
            "integrity_hash": embedding_pack.get("integrity_hash"),
        }
        _append_event(event)
        bridge["event"] = event
        bridge["paths"] = {
            "markdown": str(md_path),
            "json": str(json_path),
            "embedding": str(emb_path),
            "latest_markdown": str(latest_md),
            "latest_json": str(latest_json),
            "latest_embedding": str(latest_emb),
        }

    return bridge


def maybe_auto_bridge(
    cfg: Optional[AegisConfig] = None,
    *,
    band: Optional[str] = None,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Privileged emergency action: auto-generate bridge on emergency band."""
    cfg = cfg or load_config()
    if force:
        return generate_bridge(cfg, trigger="force")
    if not getattr(cfg, "continuity_bridge_enabled", True):
        return None
    if not getattr(cfg, "continuity_auto_on_emergency", True):
        return None
    if band != "emergency":
        return None
    return generate_bridge(cfg, trigger="emergency_band")


def latest_bridge_paths() -> Dict[str, str]:
    cdir = continuity_dir()
    return {
        "markdown": str(cdir / "latest.md"),
        "json": str(cdir / "latest.json"),
        "embedding": str(cdir / "latest_embedding_handoff.json"),
        "dir": str(cdir),
    }
