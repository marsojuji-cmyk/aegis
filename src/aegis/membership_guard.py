"""Honest local guard for ChatGPT memberships without a quota API."""

from __future__ import annotations

from typing import Any, Dict

from aegis.config import load_config
from aegis.ledger import generate_report


def membership_status() -> Dict[str, Any]:
    """Return observed local usage and a conservative policy, never a claimed quota."""
    cfg = load_config()
    report = generate_report()
    observed = int(report.get("total_tokens_consumed") or 0)
    ceiling = max(0, int(cfg.membership_shadow_weekly_tokens))
    reserve = min(0.95, max(0.0, float(cfg.membership_reserve_percent)))
    if not cfg.membership_guard_enabled:
        mode, detail = "disabled", "membership guard disabled"
    elif ceiling <= 0:
        mode, detail = "observe", "No supported personal quota feed; calibrate before enforcing a ceiling."
    else:
        mode = "conserve" if observed / float(ceiling) >= 1.0 - reserve else "normal"
        detail = "Use brief output and reuse only." if mode == "conserve" else "Normal operation."
    return {"source": "local_estimate_not_chatgpt_quota", "week": report.get("week"), "enabled": bool(cfg.membership_guard_enabled), "mode": mode, "observed_tokens": observed, "shadow_weekly_tokens": ceiling or None, "reserve_percent": round(reserve * 100, 1), "detail": detail}
