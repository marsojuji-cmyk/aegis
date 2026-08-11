"""Surplus wallet — recycle savings into investable credits (sustain first)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from aegis.config import AegisConfig, load_config
from aegis.ledger import generate_report
from aegis.paths import ensure_home, fund_path


def _default_fund() -> Dict[str, Any]:
    return {
        "available_credits": 0,
        "lifetime_saved": 0,
        "lifetime_invested": 0,
        "lifetime_credited": 0,
        "last_sync_week": None,
        "last_sync_saved": 0,
    }


def load_fund() -> Dict[str, Any]:
    ensure_home()
    path = fund_path()
    if not path.is_file():
        fund = _default_fund()
        save_fund(fund)
        return fund
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = _default_fund()
    base = _default_fund()
    base.update(data)
    return base


def save_fund(fund: Dict[str, Any]) -> None:
    ensure_home()
    fund_path().write_text(json.dumps(fund, indent=2), encoding="utf-8")


def sync_from_ledger(cfg: Optional[AegisConfig] = None) -> Dict[str, Any]:
    """
    Grow wish-jar credits from weekly savings without eating reserve.

    surplus_credit_delta = min(headroom, new_saved * reinvest_rate)
    where new_saved is savings since last sync this week (or full week on new week).
    """
    cfg = cfg or load_config()
    report = generate_report(cfg)
    fund = load_fund()

    week = report["week"]
    gross_saved = int(report["total_tokens_saved"])
    processed = int(report["total_tokens_consumed"])
    cap = int(cfg.weekly_token_cap)
    reserve_tokens = int(cap * cfg.reserve_floor)
    headroom = max(0, cap - processed - reserve_tokens)

    if fund.get("last_sync_week") != week:
        # new week: credit only from this week's savings * rate, capped by headroom
        baseline = 0
        fund["last_sync_week"] = week
    else:
        baseline = int(fund.get("last_sync_saved", 0))

    new_saved = max(0, gross_saved - baseline)
    eligible = int(new_saved * cfg.reinvest_rate)
    credit = min(headroom, eligible)

    # Only mint credits when reserve is healthy
    if report["reserve_signal"] == "ok" and credit > 0:
        fund["available_credits"] = int(fund.get("available_credits", 0)) + credit
        fund["lifetime_credited"] = int(fund.get("lifetime_credited", 0)) + credit

    fund["last_sync_saved"] = gross_saved
    fund["lifetime_saved"] = int(fund.get("lifetime_saved", 0))
    # lifetime_saved tracks cumulative tokens_saved observed (best-effort)
    if gross_saved > fund["lifetime_saved"]:
        fund["lifetime_saved"] = gross_saved

    fund["status"] = report["reserve_signal"]
    fund["headroom"] = headroom
    fund["week"] = week
    fund["gross_saved_week"] = gross_saved
    save_fund(fund)
    return fund


def surplus_snapshot(cfg: Optional[AegisConfig] = None) -> Dict[str, Any]:
    cfg = cfg or load_config()
    report = generate_report(cfg)
    fund = sync_from_ledger(cfg)
    return {
        "reserve_signal": report["reserve_signal"],
        "remaining_weekly_capacity_percent": report["remaining_weekly_capacity_percent"],
        "weekly_token_cap": cfg.weekly_token_cap,
        "reserve_floor": cfg.reserve_floor,
        "reinvest_rate": cfg.reinvest_rate,
        "gross_saved_week": report["total_tokens_saved"],
        "tokens_consumed_week": report["total_tokens_consumed"],
        "headroom": fund.get("headroom", 0),
        "available_credits": fund.get("available_credits", 0),
        "lifetime_saved": fund.get("lifetime_saved", 0),
        "lifetime_credited": fund.get("lifetime_credited", 0),
        "lifetime_invested": fund.get("lifetime_invested", 0),
        "can_invest": report["reserve_signal"] == "ok" and fund.get("available_credits", 0) > 0,
        "week": report["week"],
        "reuse_hit_rate_percent": report.get("reuse_hit_rate_percent", 0),
        "reuse_tokens_saved": report.get("reuse_tokens_saved", 0),
        "pack_attempts": report.get("pack_attempts", 0),
    }


def invest_credits(amount: int, cfg: Optional[AegisConfig] = None) -> Dict[str, Any]:
    """Deduct credits if reserve ok. Returns result dict."""
    cfg = cfg or load_config()
    snap = surplus_snapshot(cfg)
    if snap["reserve_signal"] != "ok":
        return {
            "ok": False,
            "error": f"invest frozen: reserve_signal={snap['reserve_signal']}",
            "available_credits": snap["available_credits"],
        }
    amount = int(amount)
    if amount <= 0:
        return {"ok": False, "error": "credits must be > 0"}
    fund = load_fund()
    avail = int(fund.get("available_credits", 0))
    if amount > avail:
        return {
            "ok": False,
            "error": f"insufficient credits ({avail} available)",
            "available_credits": avail,
        }
    fund["available_credits"] = avail - amount
    fund["lifetime_invested"] = int(fund.get("lifetime_invested", 0)) + amount
    save_fund(fund)
    return {
        "ok": True,
        "invested": amount,
        "available_credits": fund["available_credits"],
        "lifetime_invested": fund["lifetime_invested"],
    }
