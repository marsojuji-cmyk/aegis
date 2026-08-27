"""
Predictive weekly budget — burn trajectory, throttle ETA, recommended spend.

Production-hardened: clamped horizon, safe burn estimates, optional usage inject
(avoids double ledger scan when caller already has analyze_usage()).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aegis.config import AegisConfig, load_config
from aegis.ledger import generate_report
from aegis.usage_intel import analyze_usage


def _iso_weekday() -> int:
    return datetime.now(timezone.utc).isocalendar().weekday


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _signal_for_remaining(rem_pct: float, cfg: AegisConfig) -> str:
    if rem_pct < cfg.throttle_floor * 100:
        return "hard_stop"
    if rem_pct < cfg.reserve_floor * 100:
        return "throttle"
    return "ok"


def predict_budget(
    cfg: Optional[AegisConfig] = None,
    *,
    horizon_days: Optional[int] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Predict week-end position. Never raises — returns degraded defaults on error."""
    try:
        cfg = cfg or load_config()
        usage = usage if usage is not None else analyze_usage()
        report = generate_report(cfg)
    except Exception as exc:  # noqa: BLE001
        return {
            "week": "unknown",
            "error": str(exc),
            "projected_signal": "ok",
            "projected_remaining_pct": 100.0,
            "advice": ["forecast unavailable — check ledger"],
            "horizon_days": 7,
            "recommended_daily_budget": 0.0,
            "avg_daily_burn": 0.0,
        }

    horizon = int(horizon_days or getattr(cfg, "forecast_horizon_days", 7) or 7)
    horizon = max(1, min(horizon, 30))

    cap = max(1, _safe_int(cfg.weekly_token_cap, 1_000_000))
    consumed = max(0, _safe_int(report.get("total_tokens_consumed")))
    remaining = max(0, cap - consumed)
    rem_pct = max(0.0, min(100.0, _safe_float(report.get("remaining_weekly_capacity_percent"), 100.0)))
    capacity_left = int(cap * (rem_pct / 100.0))

    avg_burn = _safe_float(usage.get("avg_daily_burn"))
    peak_burn = _safe_float(usage.get("peak_daily_burn"))
    if avg_burn <= 0:
        avg_burn = max(500.0, consumed / max(1, _iso_weekday()))
    # hard cap: never project > 50% of weekly cap per day (insane burn protection)
    avg_burn = min(avg_burn, cap * 0.5)

    days_left_in_week = max(1, 8 - _iso_weekday())
    projected_week_end = int(consumed + avg_burn * days_left_in_week)
    projected_remaining_pct = round(
        max(0.0, (1.0 - projected_week_end / float(cap)) * 100), 2
    )
    projected_signal = _signal_for_remaining(projected_remaining_pct, cfg)

    tokens_until_reserve = max(0, int(cap * (1.0 - float(cfg.reserve_floor))) - consumed)
    tokens_until_hard = max(0, int(cap * (1.0 - float(cfg.throttle_floor))) - consumed)

    def eta_days(token_budget: int) -> Optional[float]:
        if avg_burn <= 0:
            return None
        if token_budget <= 0:
            return 0.0
        return round(token_budget / avg_burn, 2)

    safe_daily = (
        round(tokens_until_reserve / float(days_left_in_week), 1)
        if days_left_in_week
        else 0.0
    )

    trajectory: List[Dict[str, Any]] = []
    running = consumed
    for d in range(1, horizon + 1):
        running = int(running + avg_burn)
        rem = round(max(0.0, (1.0 - running / float(cap)) * 100), 2)
        trajectory.append(
            {
                "day_offset": d,
                "projected_consumed": running,
                "remaining_pct": rem,
                "signal": _signal_for_remaining(rem, cfg),
            }
        )

    out: Dict[str, Any] = {
        "week": report.get("week"),
        "horizon_days": horizon,
        "weekly_token_cap": cap,
        "consumed": consumed,
        "remaining_tokens": remaining,
        "capacity_left_tokens": capacity_left,
        "remaining_pct": rem_pct,
        "current_signal": report.get("reserve_signal") or "ok",
        "avg_daily_burn": round(avg_burn, 1),
        "peak_daily_burn": peak_burn,
        "days_left_in_week": days_left_in_week,
        "projected_week_end_consumed": projected_week_end,
        "projected_remaining_pct": projected_remaining_pct,
        "projected_signal": projected_signal,
        "eta_days_to_reserve": eta_days(tokens_until_reserve),
        "eta_days_to_hard_stop": eta_days(tokens_until_hard),
        "tokens_until_reserve": tokens_until_reserve,
        "tokens_until_hard_stop": tokens_until_hard,
        "recommended_daily_budget": safe_daily,
        "reserve_floor": float(cfg.reserve_floor),
        "throttle_floor": float(cfg.throttle_floor),
        "trajectory": trajectory,
        "advice": _advice(
            projected_signal,
            rem_pct,
            _safe_float(usage.get("cache_hit_rate_percent")),
            safe_daily,
            avg_burn,
            cfg,
        ),
        "cache_hit_threshold": float(
            getattr(cfg, "cache_hit_threshold", 30.0) or 30.0
        ),
        "burn_warning_multiplier": float(
            getattr(cfg, "burn_warning_multiplier", 1.25) or 1.25
        ),
        "burn_status": None,
        "burn_warning": None,
    }
    # Progressive burn status (SSOT: aegis.burn) — pass forecast to avoid recursion
    try:
        from aegis.burn import burn_status as _burn_status

        bs = _burn_status(cfg, usage=usage, forecast=out, record_events=True)
        out["burn_status"] = {
            k: bs.get(k)
            for k in (
                "level",
                "ratio",
                "ratio_pct",
                "message",
                "fix",
                "fix_detail",
                "bands",
                "budget_aware",
                "top_consumers",
            )
        }
        out["burn_warning"] = bs.get("burn_warning")
        if bs.get("level") in ("caution", "warn", "critical"):
            msg = bs.get("message")
            if msg and msg not in (out.get("advice") or []):
                adv = list(out.get("advice") or [])
                # insert before trailing "Stay ≤ …" line when present
                if adv and adv[-1].startswith("Stay ≤"):
                    out["advice"] = adv[:-1] + [msg] + [adv[-1]]
                else:
                    out["advice"] = adv + [msg]
    except Exception:  # noqa: BLE001
        out["burn_warning"] = burn_warning_payload(avg_burn, safe_daily, cfg)
    return out


def burn_warning_payload(
    avg_daily_burn: float,
    safe_daily: float,
    cfg: AegisConfig,
) -> Optional[Dict[str, Any]]:
    """
    Critical-only structured warning (ratio ≥ burn_warning_multiplier).

    Prefer burn_status() for progressive levels; this remains for back-compat.
    """
    try:
        from aegis.burn import level_for_ratio, burn_ratio, message_for_level, fix_for_level

        ratio = burn_ratio(avg_daily_burn, safe_daily)
        level = level_for_ratio(ratio, cfg)
        if level != "critical":
            return None
        mult = float(getattr(cfg, "burn_warning_multiplier", 1.25) or 1.25)
        msg = message_for_level(
            level,
            avg_daily_burn=avg_daily_burn,
            safe_daily=safe_daily,
            ratio=ratio,
            cfg=cfg,
        )
        fix = fix_for_level(level)
        return {
            "active": True,
            "level": level,
            "avg_daily_burn": round(avg_daily_burn, 1),
            "safe_daily": safe_daily,
            "over_pct": max(0.0, round((ratio - 1.0) * 100.0, 0)),
            "multiplier": mult,
            "message": msg,
            **fix,
        }
    except Exception:  # noqa: BLE001
        mult = float(getattr(cfg, "burn_warning_multiplier", 1.25) or 1.25)
        if safe_daily <= 0 or avg_daily_burn <= safe_daily * mult:
            return None
        over_pct = round((avg_daily_burn / safe_daily - 1.0) * 100.0, 0)
        return {
            "active": True,
            "avg_daily_burn": round(avg_daily_burn, 1),
            "safe_daily": safe_daily,
            "over_pct": over_pct,
            "multiplier": mult,
            "message": (
                f"Daily burn {avg_daily_burn:.0f} tok/day is ~{over_pct:.0f}% over safe "
                f"allowance {safe_daily:.0f}/day (threshold {mult:.0%} of safe). "
                f"Cut fan-out: fewer parallel tasks and smaller batches."
            ),
            "fix": "cut_fan_out",
            "fix_detail": (
                "Reduce parallel tasks and batch size so daily spend returns "
                "to ≤ safe daily allowance."
            ),
        }


def burn_warning_message(
    avg_daily_burn: float,
    safe_daily: float,
    cfg: AegisConfig,
) -> Optional[str]:
    """Plain-text critical burn warning (or None)."""
    payload = burn_warning_payload(avg_daily_burn, safe_daily, cfg)
    return None if not payload else str(payload["message"])


def _advice(
    projected_signal: str,
    rem_pct: float,
    cache_hit: float,
    safe_daily: float,
    avg_daily_burn: float,
    cfg: AegisConfig,
) -> List[str]:
    """Build human-readable forecast tips from burn + cache signals."""
    tips: List[str] = []
    cache_hit_threshold = float(getattr(cfg, "cache_hit_threshold", 30.0) or 30.0)

    if projected_signal == "hard_stop":
        tips.append("Projected hard_stop — throttle to mock/reuse-only until week rolls.")
    elif projected_signal == "throttle":
        tips.append("Projected throttle — prefer explore packs + output shrink.")
    else:
        tips.append("On track to clear reserve floor — compound reinvest is safe.")
    if cache_hit < cache_hit_threshold:
        tips.append(
            f"Cache hit {cache_hit}% — auto-cache optimizer will widen fallbacks."
        )
    burn_msg = burn_warning_message(avg_daily_burn, safe_daily, cfg)
    if burn_msg:
        tips.append(burn_msg)
    if safe_daily <= 0:
        tips.append("No spend headroom — reuse-only until week rolls.")
    else:
        tips.append(f"Stay ≤ {safe_daily:.0f} processed tokens/day to protect reserve.")
    return tips
