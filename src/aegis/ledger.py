"""Durable append-only token ledger (the piggy bank)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aegis.config import AegisConfig, load_config
from aegis.paths import ensure_home, ledger_path


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _week_key(ts: Optional[str] = None) -> str:
    if ts:
        # ISO week from timestamp prefix
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def estimate_tokens(text: str) -> int:
    """Backward-compatible; prefer aegis.tokens for annotation-aware counts."""
    from aegis.tokens import estimate_tokens as _est

    return _est(text)


def record(
    *,
    kind: str,
    task: str = "",
    mode: str = "",
    raw_in: int = 0,
    processed_in: int = 0,
    raw_out: int = 0,
    processed_out: int = 0,
    pack_id: Optional[str] = None,
    reuse: bool = False,
    project: str = "aegis",
    meta: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    cfg: Optional[AegisConfig] = None,
    source: str = "local_counterfactual",
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = cfg or load_config()
    normalized_request_id = request_id.strip() if request_id else None
    if not dry_run and normalized_request_id and any(
        row.get("request_id") == normalized_request_id for row in read_all()
    ):
        raise ValueError(f"ledger request_id already recorded: {normalized_request_id}")
    tokens_saved = max(0, (raw_in - processed_in) + (raw_out - processed_out))
    cost_in_raw = (raw_in / 1000.0) * cfg.cost_per_1k_input
    cost_in_act = (processed_in / 1000.0) * cfg.cost_per_1k_input
    cost_out_raw = (raw_out / 1000.0) * cfg.cost_per_1k_output
    cost_out_act = (processed_out / 1000.0) * cfg.cost_per_1k_output
    entry = {
        "id": f"txn_{uuid.uuid4().hex[:12]}",
        "ts": _now(),
        "week": _week_key(),
        "kind": kind,
        "task": task,
        "mode": mode,
        "raw_in": int(raw_in),
        "processed_in": int(processed_in),
        "raw_out": int(raw_out),
        "processed_out": int(processed_out),
        "tokens_saved": int(tokens_saved),
        "pack_id": pack_id,
        "reuse": bool(reuse),
        "project": project,
        "source": source,
        "request_id": normalized_request_id,
        "meta": meta or {},
        "cost_without": round(cost_in_raw + cost_out_raw, 6),
        "cost_with": round(cost_in_act + cost_out_act, 6),
        "savings_dollars": round(
            (cost_in_raw + cost_out_raw) - (cost_in_act + cost_out_act), 6
        ),
    }
    if not dry_run:
        ensure_home()
        with ledger_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_all() -> List[Dict[str, Any]]:
    path = ledger_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def filter_week(
    rows: Optional[List[Dict[str, Any]]] = None,
    week: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows = rows if rows is not None else read_all()
    week = week or _week_key()
    return [r for r in rows if r.get("week") == week]


def reserve_signal(remaining_pct: float, cfg: Optional[AegisConfig] = None) -> str:
    cfg = cfg or load_config()
    # remaining_pct is 0–100 style capacity left
    floor_pct = cfg.reserve_floor * 100.0
    hard_pct = cfg.throttle_floor * 100.0
    if remaining_pct >= floor_pct:
        return "ok"
    if remaining_pct >= hard_pct:
        return "throttle"
    return "hard_stop"


def generate_report(
    cfg: Optional[AegisConfig] = None,
    week: Optional[str] = None,
    accounting: str = "local",
) -> Dict[str, Any]:
    cfg = cfg or load_config()
    week = week or _week_key()
    all_rows = read_all()
    rows = filter_week(all_rows, week)

    # Production economics only admits provider-observed events. Local packing
    # remains useful context telemetry and is the default for internal control.
    observed = [r for r in rows if r.get("source") == "provider_observed"]
    selected = observed if accounting == "provider_observed" else rows
    raw_in = sum(int(r.get("raw_in", 0)) for r in selected)
    proc_in = sum(int(r.get("processed_in", 0)) for r in selected)
    raw_out = sum(int(r.get("raw_out", 0)) for r in selected)
    proc_out = sum(int(r.get("processed_out", 0)) for r in selected)
    saved = sum(int(r.get("tokens_saved", 0)) for r in selected)
    local_saved = sum(int(r.get("tokens_saved", 0)) for r in rows if r not in observed)
    processed_total = proc_in + proc_out
    raw_total = raw_in + raw_out
    reduction = round((saved / (raw_total + 1e-5)) * 100, 1)
    rem_pct = round((1.0 - (processed_total / float(cfg.weekly_token_cap))) * 100, 2)
    rem_pct = max(0.0, rem_pct)
    signal = reserve_signal(rem_pct, cfg)

    # Pack reuse dashboard (compounding signal)
    pack_misses = sum(1 for r in rows if r.get("kind") == "pack" and not r.get("reuse"))
    reuse_hits = sum(1 for r in rows if r.get("kind") == "reuse_hit" or r.get("reuse"))
    pack_attempts = pack_misses + reuse_hits
    reuse_hit_rate = (
        round((reuse_hits / float(pack_attempts)) * 100.0, 1) if pack_attempts else 0.0
    )
    reuse_tokens_saved = sum(
        int(r.get("tokens_saved", 0))
        for r in rows
        if r.get("kind") == "reuse_hit" or r.get("reuse")
    )
    lifetime_reuse_hits = sum(
        1 for r in all_rows if r.get("kind") == "reuse_hit" or r.get("reuse")
    )
    lifetime_pack_misses = sum(
        1 for r in all_rows if r.get("kind") == "pack" and not r.get("reuse")
    )
    lifetime_pack_attempts = lifetime_reuse_hits + lifetime_pack_misses
    lifetime_reuse_hit_rate = (
        round((lifetime_reuse_hits / float(lifetime_pack_attempts)) * 100.0, 1)
        if lifetime_pack_attempts
        else 0.0
    )

    selected_financial_savings = round(
        sum(float(r.get("savings_dollars", 0)) for r in selected), 4
    )
    local_counterfactual_financial_savings = round(
        sum(float(r.get("savings_dollars", 0)) for r in rows if r not in observed), 4
    )

    return {
        "source": "durable_ledger",
        "accounting": accounting,
        "production_accounting": "provider_observed_only",
        "observed_transactions": len(observed),
        "local_counterfactual_tokens_saved": local_saved,
        "week": week,
        "total_transactions": len(rows),
        "lifetime_transactions": len(all_rows),
        "total_raw_tokens_demanded": raw_total,
        "total_tokens_consumed": processed_total,
        "total_tokens_saved": saved,
        "raw_in": raw_in,
        "processed_in": proc_in,
        "raw_out": raw_out,
        "processed_out": proc_out,
        "overall_token_reduction_percent": reduction,
        "weekly_token_cap": cfg.weekly_token_cap,
        "remaining_weekly_capacity_percent": rem_pct,
        "reserve_floor": cfg.reserve_floor,
        "reserve_signal": signal,
        "reuse_hits": reuse_hits,
        "pack_misses": pack_misses,
        "pack_attempts": pack_attempts,
        "reuse_hit_rate_percent": reuse_hit_rate,
        "reuse_tokens_saved": reuse_tokens_saved,
        "lifetime_reuse_hits": lifetime_reuse_hits,
        "lifetime_pack_attempts": lifetime_pack_attempts,
        "lifetime_reuse_hit_rate_percent": lifetime_reuse_hit_rate,
        # Never surface modeled local savings as provider-observed economics.
        "net_financial_savings_dollars": selected_financial_savings,
        "local_counterfactual_financial_savings_dollars": local_counterfactual_financial_savings,
        "transactions": rows,
    }


def import_legacy_expense_once(report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Seed one synthetic txn from gen-1 expense report if not yet imported."""
    from aegis.paths import legacy_import_flag

    flag = legacy_import_flag()
    ensure_home()
    if flag.is_file():
        return None
    if not report:
        flag.write_text("empty\n", encoding="utf-8")
        return None

    raw = int(report.get("total_raw_tokens_demanded", 0) or 0)
    proc = int(report.get("total_tokens_consumed", 0) or 0)
    if raw <= 0 and proc <= 0:
        flag.write_text("empty\n", encoding="utf-8")
        return None

    entry = record(
        kind="legacy_import",
        task="import:expense_report_output.json",
        mode="import",
        raw_in=raw,
        processed_in=proc,
        meta={"source": "legacy_expense_report", "note": "one-time seed"},
    )
    flag.write_text(entry["id"] + "\n", encoding="utf-8")
    return entry
