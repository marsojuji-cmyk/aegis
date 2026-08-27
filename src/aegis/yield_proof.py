"""Honest economic-yield harness.

Fixture naive-vs-pack is labeled counterfactual_chars4.
savings_percent is observed billed USD on matched_provider_pairs, else null.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from aegis.paths import hermes_token_pairs_path


ACCOUNTING = "counterfactual_chars4"


def admitted_pair_present() -> bool:
    path = hermes_token_pairs_path()
    if not path.is_file():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            if '"admitted": true' in line or '"admitted":true' in line:
                return True
    except OSError:
        return False
    return False


def _naive_chars(paths: Sequence[str]) -> int:
    total = 0
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            total += p.stat().st_size
    return total


def prove(paths: Sequence[str], *, task: str = "yield-prove") -> Dict[str, Any]:
    from aegis.bento import assemble
    from aegis.pack_cache import attach_reuse_meta, get_or_none, save_pack

    files = [str(Path(p).expanduser().resolve()) for p in paths if Path(p).is_file()]
    if not files:
        return {"ok": False, "error": "no readable files", "savings_percent": None}
    snippets: List[Dict[str, str]] = []
    for path in files:
        snippets.append(
            {
                "path": path,
                "content": Path(path).read_text(encoding="utf-8", errors="replace"),
            }
        )
    naive = _naive_chars(files)
    naive_tok = naive // 4
    t0 = time.perf_counter()
    pack_id, cached, meta = get_or_none("explore", files, task)
    if cached is None:
        payload = assemble(core_task=task, code_snippets=snippets, mode="explore")
        attach_reuse_meta(payload, files, "explore")
        save_pack(pack_id, payload)
        reuse = False
    else:
        payload = cached
        reuse = True
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    packed_tok = int(
        payload.get("total_compressed_tokens")
        or payload.get("compressed_tokens")
        or payload.get("tokens")
        or 0
    )
    if packed_tok <= 0:
        text = str(payload.get("bento") or payload.get("text") or "")
        packed_tok = max(1, len(text) // 4)
    saved = max(0, naive_tok - packed_tok)
    reduction = round((saved / float(naive_tok)) * 100.0, 1) if naive_tok else 0.0
    admitted = admitted_pair_present()
    return {
        "ok": True,
        "accounting": ACCOUNTING,
        "savings_percent": None,
        "admitted_pair": admitted,
        "naive_bytes": naive,
        "naive_tokens": naive_tok,
        "packed_tokens": packed_tok,
        "tokens_saved_counterfactual": saved,
        "reduction_percent_counterfactual": reduction,
        "reuse": reuse,
        "pack_id": pack_id,
        "fallback_used": bool(meta.get("fallback_used")),
        "elapsed_ms": elapsed_ms,
        "paths": files,
        "note": "reduction is chars/4 local counterfactual; not model savings",
    }


def bench(paths: Sequence[str], *, rounds: int = 12, task: str = "bench") -> Dict[str, Any]:
    files = [str(Path(p).expanduser().resolve()) for p in paths if Path(p).is_file()]
    if not files:
        return {"ok": False, "error": "no readable files"}
    cold: List[float] = []
    warm: List[float] = []
    naive: List[float] = []
    from aegis.pack_cache import file_hash, get_or_none
    from aegis.yield_proof import prove as _prove

    for _ in range(max(1, rounds)):
        t0 = time.perf_counter()
        for f in files:
            Path(f).read_text(encoding="utf-8", errors="replace")
        naive.append((time.perf_counter() - t0) * 1000.0)
        t1 = time.perf_counter()
        for f in files:
            file_hash(f)
        cold.append((time.perf_counter() - t1) * 1000.0)
        t2 = time.perf_counter()
        for f in files:
            file_hash(f)
        warm.append((time.perf_counter() - t2) * 1000.0)
        get_or_none("explore", files, task)

    def _pct(vals: List[float], p: float) -> float:
        if not vals:
            return 0.0
        ordered = sorted(vals)
        idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
        return round(ordered[idx], 3)

    proof = _prove(files, task=task)
    speedup = None
    if _pct(warm, 50) > 0:
        speedup = round(_pct(cold, 50) / max(_pct(warm, 50), 0.001), 2)
    return {
        "ok": True,
        "rounds": rounds,
        "naive_read_ms_p50": _pct(naive, 50),
        "hash_cold_ms_p50": _pct(cold, 50),
        "hash_warm_ms_p50": _pct(warm, 50),
        "hash_warm_ms_p95": _pct(warm, 95),
        "hash_cache_speedup_x": speedup,
        "yield": proof,
        "savings_percent": None,
    }


def _mean(values: List[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / float(len(values)), 6)


def _observed_usd(row: Dict[str, Any]) -> float | None:
    from aegis.outcomes import OBSERVED_COST_STATUSES, UNTRUSTED_ROUTING_COST_SOURCES

    source = str(row.get("cost_source") or "").strip().lower()
    if row.get("cost_status") not in OBSERVED_COST_STATUSES:
        return None
    if not source or source in UNTRUSTED_ROUTING_COST_SOURCES:
        return None
    usd = row.get("cost_usd")
    if not isinstance(usd, (int, float)):
        return None
    return float(usd)


def billed_pair_snapshot() -> Dict[str, Any]:
    """Live matched-pair dollars. savings_percent is observed USD, not AA ranks."""
    from aegis.outcomes import load_outcome_evidence, outcome_report
    from aegis.receipt_collect import PAIR_WORKFLOW

    report = outcome_report(workflow=PAIR_WORKFLOW)
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in load_outcome_evidence()["rows"]:
        if row.get("workflow") != PAIR_WORKFLOW:
            continue
        grouped.setdefault(str(row["task_id"]), {})[str(row["variant"])] = row
    baseline_usd: List[float] = []
    governed_usd: List[float] = []
    for pair in grouped.values():
        if "baseline" not in pair or "governed" not in pair:
            continue
        base = _observed_usd(pair["baseline"])
        gov = _observed_usd(pair["governed"])
        if base is None or gov is None:
            continue
        baseline_usd.append(base)
        governed_usd.append(gov)
    paired = int(report.get("paired_tasks") or 0)
    return {
        "workflow": PAIR_WORKFLOW,
        "paired_tasks": paired,
        "observed_cost_pairs": int(report.get("observed_cost_pairs") or 0),
        "cost_comparison_complete": bool(report.get("cost_comparison_complete")),
        "baseline_mean_usd": _mean(baseline_usd),
        "governed_mean_usd": _mean(governed_usd),
        "total_cost_usd_saved": report.get("total_cost_usd_saved"),
        "savings_percent": report.get("savings_percent"),
        "mean_seconds_saved": report.get("mean_seconds_saved"),
        "acceptance_delta": report.get("acceptance_delta"),
        "outcome_decision": report.get("decision"),
        "routing_authorized": bool(report.get("routing_authorized")),
        "routing_scope": "tiny_chat" if report.get("routing_authorized") else "off",
    }


def yield_is_honest(yld: Dict[str, Any]) -> bool:
    """True when savings_percent is absent or matches billed USD math."""
    pct = yld.get("savings_percent")
    billed = yld.get("billed_pairs") or {}
    billed_pct = billed.get("savings_percent")
    if pct is None:
        return billed_pct is None or int(billed.get("observed_cost_pairs") or 0) == 0
    if billed_pct is None:
        return False
    try:
        return abs(float(pct) - float(billed_pct)) < 0.15
    except (TypeError, ValueError):
        return False


def yield_report() -> Dict[str, Any]:
    from aegis.ledger import generate_report
    from aegis.routing import workflow_compare

    report = generate_report()
    billed = billed_pair_snapshot()
    saved = int(report.get("total_tokens_saved") or 0)
    consumed = int(report.get("total_tokens_consumed") or 0)
    reduction = report.get("overall_token_reduction_percent")
    reuse = report.get("reuse_hit_rate_percent")
    compare = workflow_compare()
    return {
        "ok": True,
        "accounting": ACCOUNTING,
        "savings_percent": billed.get("savings_percent"),
        "savings_percent_accounting": "observed_billed_usd" if billed.get("savings_percent") is not None else None,
        "admitted_pair": admitted_pair_present(),
        "ledger_tokens_saved_local": saved,
        "ledger_tokens_consumed": consumed,
        "ledger_reduction_percent_local": 0.0 if reduction is None else float(reduction),
        "reuse_hit_rate": 0.0 if reuse is None else float(reuse),
        "billed_pairs": billed,
        "workflow_compare": compare,
        "routing_authorized": bool(billed.get("routing_authorized")),
        "routing_scope": billed.get("routing_scope") or "off",
        "note": "savings_percent is billed USD on matched_provider_pairs. ledger reduction is chars/4 counterfactual. implement packs are not routed.",
    }
