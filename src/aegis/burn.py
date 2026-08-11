"""
Burn status — single source of truth for safe-daily ratios, progressive levels,
event log, and budget-aware fan-out guidance.

Levels (ratio = avg_daily_burn / safe_daily):
  ok       < burn_caution_multiplier   (default 0.80)
  caution  ≥ 0.80 and < burn_warn_multiplier (1.00)
  warn     ≥ 1.00 and < burn_warning_multiplier (1.25)
  critical ≥ 1.25  → cut fan-out (parallel tasks / batch size)

All copy for menu bar / dashboard / weekly report comes from burn_status().
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aegis.config import AegisConfig, load_config
from aegis.forecast import predict_budget
from aegis.paths import burn_events_path, burn_state_path, ensure_home
from aegis.usage_intel import analyze_usage

_LOCK = threading.RLock()

LEVEL_ORDER = {"ok": 0, "caution": 1, "warn": 2, "critical": 3}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def burn_ratio(avg_daily_burn: float, safe_daily: float) -> float:
    if safe_daily <= 0:
        return 0.0
    return round(avg_daily_burn / safe_daily, 4)


def level_for_ratio(ratio: float, cfg: AegisConfig) -> str:
    caution = float(getattr(cfg, "burn_caution_multiplier", 0.80) or 0.80)
    warn = float(getattr(cfg, "burn_warn_multiplier", 1.00) or 1.00)
    critical = float(getattr(cfg, "burn_warning_multiplier", 1.25) or 1.25)
    if ratio >= critical:
        return "critical"
    if ratio >= warn:
        return "warn"
    if ratio >= caution:
        return "caution"
    return "ok"


def message_for_level(
    level: str,
    *,
    avg_daily_burn: float,
    safe_daily: float,
    ratio: float,
    cfg: AegisConfig,
) -> str:
    """Tone + actionability for progressive disclosure."""
    mult = float(getattr(cfg, "burn_warning_multiplier", 1.25) or 1.25)
    over_pct = max(0.0, round((ratio - 1.0) * 100.0, 0)) if ratio >= 1.0 else 0.0
    if level == "ok":
        return (
            f"Burn healthy: {avg_daily_burn:.0f}/day ≤ "
            f"{float(getattr(cfg, 'burn_caution_multiplier', 0.8)) * 100:.0f}% of safe "
            f"{safe_daily:.0f}/day. No action needed."
        )
    if level == "caution":
        return (
            f"Approaching limit: burn {avg_daily_burn:.0f}/day is "
            f"{ratio:.0%} of safe {safe_daily:.0f}/day. "
            f"Prefer explore packs; avoid large implement batches."
        )
    if level == "warn":
        return (
            f"At or over safe allowance: burn {avg_daily_burn:.0f}/day "
            f"({ratio:.0%} of safe {safe_daily:.0f}/day). "
            f"Pause non-critical fan-out; wait for daily average to cool, "
            f"or upgrade weekly cap only if reserve allows."
        )
    # critical
    return (
        f"Daily burn {avg_daily_burn:.0f} tok/day is ~{over_pct:.0f}% over safe "
        f"allowance {safe_daily:.0f}/day (threshold {mult:.0%} of safe). "
        f"Cut fan-out: fewer parallel tasks and smaller batches."
    )


def fix_for_level(level: str) -> Dict[str, str]:
    if level == "ok":
        return {
            "fix": "none",
            "fix_detail": "Stay within safe daily allowance.",
        }
    if level == "caution":
        return {
            "fix": "trim_batches",
            "fix_detail": "Reduce batch size slightly; defer low-priority implement runs.",
        }
    if level == "warn":
        return {
            "fix": "pause_noncritical",
            "fix_detail": (
                "Pause non-critical parallel work; keep only high-ROI tasks until "
                "avg burn drops under safe daily."
            ),
        }
    return {
        "fix": "cut_fan_out",
        "fix_detail": (
            "Reduce parallel tasks and batch size so daily spend returns "
            "to ≤ safe daily allowance."
        ),
    }


def _load_burn_state() -> Dict[str, Any]:
    ensure_home()
    path = burn_state_path()
    if not path.is_file():
        return {"last_level": "ok", "last_ratio": 0.0, "updated_ts": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"last_level": "ok"}
    except (OSError, json.JSONDecodeError):
        return {"last_level": "ok"}


def _save_burn_state(state: Dict[str, Any]) -> None:
    ensure_home()
    burn_state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def _append_event(event: Dict[str, Any]) -> None:
    ensure_home()
    with burn_events_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def record_level_transition(
    prev: str,
    level: str,
    *,
    ratio: float,
    avg_daily_burn: float,
    safe_daily: float,
    week: str,
) -> Optional[Dict[str, Any]]:
    """Log threshold cross / recovery when level changes."""
    if prev == level:
        return None
    direction = "up" if LEVEL_ORDER.get(level, 0) > LEVEL_ORDER.get(prev, 0) else "down"
    event = {
        "ts": _now(),
        "kind": "level_change",
        "from_level": prev,
        "to_level": level,
        "direction": direction,
        "ratio": ratio,
        "avg_daily_burn": avg_daily_burn,
        "safe_daily": safe_daily,
        "week": week,
        "crossed_125": level == "critical" and prev != "critical",
        "recovered_under_safe": level in ("ok", "caution") and prev in ("warn", "critical"),
    }
    with _LOCK:
        _append_event(event)
        _save_burn_state(
            {
                "last_level": level,
                "last_ratio": ratio,
                "updated_ts": event["ts"],
                "last_event": event,
            }
        )
    return event


def top_burn_consumers(usage: Optional[Dict[str, Any]] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Top ledger kinds/modes contributing to processed burn this week."""
    usage = usage or analyze_usage()
    kinds = usage.get("kind_distribution") or {}
    modes = usage.get("mode_distribution") or {}
    # approximate share by count (token-level needs ledger scan — good enough for summary)
    total_k = sum(int(v) for v in kinds.values()) or 1
    total_m = sum(int(v) for v in modes.values()) or 1
    by_kind = [
        {"dimension": "kind", "name": k, "count": int(v), "share_pct": round(100.0 * int(v) / total_k, 1)}
        for k, v in sorted(kinds.items(), key=lambda kv: -int(kv[1]))[:limit]
    ]
    by_mode = [
        {"dimension": "mode", "name": k, "count": int(v), "share_pct": round(100.0 * int(v) / total_m, 1)}
        for k, v in sorted(modes.items(), key=lambda kv: -int(kv[1]))[:limit]
    ]
    return by_kind + by_mode


def burn_status(
    cfg: Optional[AegisConfig] = None,
    *,
    usage: Optional[Dict[str, Any]] = None,
    forecast: Optional[Dict[str, Any]] = None,
    record_events: bool = True,
) -> Dict[str, Any]:
    """
    Live burn health-check payload for /v1/aegis/burn, weekly reports, UI.

    Config is the single source of truth for band multipliers.
    """
    cfg = cfg or load_config()
    usage = usage if usage is not None else analyze_usage()
    forecast = forecast if forecast is not None else predict_budget(cfg, usage=usage)

    avg = _safe_float(forecast.get("avg_daily_burn") or usage.get("avg_daily_burn"))
    safe = _safe_float(forecast.get("recommended_daily_budget"))
    ratio = burn_ratio(avg, safe)
    level = level_for_ratio(ratio, cfg) if safe > 0 else "ok"
    msg = message_for_level(
        level, avg_daily_burn=avg, safe_daily=safe, ratio=ratio, cfg=cfg
    )
    fix = fix_for_level(level)

    caution_m = float(getattr(cfg, "burn_caution_multiplier", 0.80) or 0.80)
    warn_m = float(getattr(cfg, "burn_warn_multiplier", 1.00) or 1.00)
    crit_m = float(getattr(cfg, "burn_warning_multiplier", 1.25) or 1.25)

    event = None
    if record_events:
        with _LOCK:
            st = _load_burn_state()
            prev = str(st.get("last_level") or "ok")
        event = record_level_transition(
            prev,
            level,
            ratio=ratio,
            avg_daily_burn=avg,
            safe_daily=safe,
            week=str(forecast.get("week") or usage.get("week") or ""),
        )
        if event is None:
            # still refresh state snapshot
            with _LOCK:
                _save_burn_state(
                    {
                        "last_level": level,
                        "last_ratio": ratio,
                        "updated_ts": _now(),
                        "last_event": st.get("last_event"),
                    }
                )

    consumers = top_burn_consumers(usage)
    workers = budget_aware_workers(cfg=cfg, level=level)

    # structured burn_warning for critical (back-compat with existing UI)
    burn_warning = None
    if level == "critical":
        burn_warning = {
            "active": True,
            "level": level,
            "avg_daily_burn": avg,
            "safe_daily": safe,
            "over_pct": max(0.0, round((ratio - 1.0) * 100.0, 0)),
            "multiplier": crit_m,
            "message": msg,
            **fix,
        }

    return {
        "ok": True,
        "ts": _now(),
        "week": forecast.get("week") or usage.get("week"),
        "level": level,
        "severity": level,  # alias for UI
        "ratio": ratio,
        "ratio_pct": round(ratio * 100.0, 1),
        "avg_daily_burn": avg,
        "safe_daily": safe,
        "peak_daily_burn": _safe_float(forecast.get("peak_daily_burn")),
        "bands": {
            "caution_at": caution_m,
            "warn_at": warn_m,
            "critical_at": crit_m,
        },
        "config": {
            "burn_caution_multiplier": caution_m,
            "burn_warn_multiplier": warn_m,
            "burn_warning_multiplier": crit_m,
            "budget_aware_mode": bool(getattr(cfg, "budget_aware_mode", True)),
        },
        "message": msg,
        "fix": fix["fix"],
        "fix_detail": fix["fix_detail"],
        "burn_warning": burn_warning,
        "progressive": {
            "ok": "healthy — no action",
            "caution": "subtle — prefer explore, trim batches",
            "warn": "strong — pause non-critical fan-out",
            "critical": "cut fan-out — fewer parallel tasks / smaller batches",
        },
        "budget_aware": {
            "enabled": bool(getattr(cfg, "budget_aware_mode", True)),
            "recommended_workers": workers,
            "default_workers": workers if level == "ok" else None,
        },
        "top_consumers": consumers,
        "event": event,
        "reserve_signal": forecast.get("current_signal") or usage.get("reserve_signal"),
        "remaining_pct": forecast.get("remaining_pct") or usage.get("remaining_pct"),
    }


def budget_aware_workers(
    default: Optional[int] = None,
    *,
    cfg: Optional[AegisConfig] = None,
    level: Optional[str] = None,
) -> int:
    """Soft-reduce concurrent batch workers as burn rises (budget-aware mode)."""
    from aegis import DEFAULT_BATCH_WORKERS

    cfg = cfg or load_config()
    base = int(default if default is not None else DEFAULT_BATCH_WORKERS)
    if not getattr(cfg, "budget_aware_mode", True):
        return base
    if level is None:
        try:
            level = str(burn_status(cfg, record_events=False).get("level") or "ok")
        except Exception:  # noqa: BLE001
            level = "ok"
    if level == "critical":
        return max(1, base // 4)
    if level == "warn":
        return max(2, base // 2)
    if level == "caution":
        return max(4, int(base * 0.75))
    return base


def burn_summary_table(status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compact table block for weekly reports."""
    st = status if status is not None else burn_status(record_events=False)
    return {
        "level": st.get("level"),
        "ratio_pct": st.get("ratio_pct"),
        "avg_daily_burn": st.get("avg_daily_burn"),
        "safe_daily": st.get("safe_daily"),
        "bands": st.get("bands"),
        "message": st.get("message"),
        "fix_detail": st.get("fix_detail"),
        "top_consumers": st.get("top_consumers"),
        "recommended_workers": (st.get("budget_aware") or {}).get("recommended_workers"),
        "event": st.get("event"),
    }


def recent_burn_events(limit: int = 20) -> List[Dict[str, Any]]:
    path = burn_events_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return list(reversed(rows[-max(1, limit) :]))
