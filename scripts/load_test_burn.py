#!/usr/bin/env python3
"""
Controlled burn threshold load-test.

Walks synthetic burn ratios through ok → caution → warn → critical and
asserts identical progressive messaging across:
  - burn_status() payload
  - forecast.burn_status / burn_warning
  - weekly markdown Burn health section
  - config SSOT (change multiplier → critical band moves)

Usage:
  python3 scripts/load_test_burn.py
  AEGIS_HOME=/tmp/aegis-burn-test python3 scripts/load_test_burn.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# ensure product src on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="aegis-burn-")
    os.environ["AEGIS_HOME"] = tmp
    print(f"[load_test_burn] AEGIS_HOME={tmp}")

    from aegis.burn import burn_status, level_for_ratio, message_for_level
    from aegis.config import AegisConfig, save_config
    from aegis.forecast import burn_warning_payload
    from aegis.intelligence import _format_weekly_md

    cfg = AegisConfig()
    save_config(cfg)
    safe = 1000.0
    scenarios = [
        (500, "ok"),
        (850, "caution"),
        (1000, "warn"),
        (1100, "warn"),
        (1250, "critical"),
        (2000, "critical"),
    ]
    failures = 0
    last_msg = {}

    for burn, expect in scenarios:
        ratio = burn / safe
        level = level_for_ratio(ratio, cfg)
        msg = message_for_level(
            level, avg_daily_burn=burn, safe_daily=safe, ratio=ratio, cfg=cfg
        )
        fc = {
            "week": "loadtest",
            "avg_daily_burn": burn,
            "recommended_daily_budget": safe,
            "peak_daily_burn": burn,
            "current_signal": "ok",
            "remaining_pct": 90,
            "projected_signal": "ok",
            "projected_remaining_pct": 80,
            "burn_warning_multiplier": cfg.burn_warning_multiplier,
            "advice": [],
        }
        st = burn_status(
            cfg,
            usage={
                "week": "loadtest",
                "kind_distribution": {"pack": 10, "router_run": 3},
                "mode_distribution": {"implement": 8, "explore": 2},
            },
            forecast=fc,
            record_events=True,
        )
        fc["burn_status"] = {
            "level": st["level"],
            "ratio_pct": st["ratio_pct"],
            "message": st["message"],
            "fix_detail": st["fix_detail"],
            "bands": st["bands"],
            "avg_daily_burn": burn,
            "safe_daily": safe,
            "top_consumers": st["top_consumers"],
            "recommended_workers": st["budget_aware"]["recommended_workers"],
        }
        fc["burn_warning"] = st.get("burn_warning")
        md = _format_weekly_md(
            {
                "week": "loadtest",
                "generated_ts": "t",
                "layer_version": "1.1.1",
                "usage": {
                    "reserve_signal": "ok",
                    "remaining_pct": 90,
                    "tokens_saved": 1,
                    "reduction_percent": 50,
                    "cache_hit_rate_percent": 20,
                },
                "forecast": fc,
                "surplus": {
                    "available_credits": 0,
                    "lifetime_saved": 0,
                    "lifetime_invested": 0,
                    "can_invest": False,
                },
                "tick_actions": [],
                "ideas": [],
                "compound_message": "x",
            }
        )

        ok = level == expect and st["level"] == expect
        if expect == "critical":
            ok = ok and st.get("burn_warning") and "fan-out" in (st["message"] or "").lower()
            ok = ok and "fan-out" in md.lower()
            ok = ok and burn_warning_payload(burn, safe, cfg) is not None
        if expect != "ok":
            ok = ok and st["message"] == msg
            ok = ok and msg in md

        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(
            f"  [{status}] burn={burn} expect={expect} got={st['level']} "
            f"ratio={st.get('ratio_pct')}% workers={st['budget_aware']['recommended_workers']}"
        )
        last_msg[expect] = st["message"]

    # SSOT: raise critical to 1.5 → 1250 should become warn
    cfg2 = AegisConfig(burn_warning_multiplier=1.50)
    save_config(cfg2)
    assert level_for_ratio(1.25, cfg2) == "warn"
    assert level_for_ratio(1.50, cfg2) == "critical"
    print("  [PASS] config SSOT: critical_at=1.50 moves band")

    # identical critical wording sample
    print("\n[sample critical copy]")
    print(" ", last_msg.get("critical", "")[:200])

    if failures:
        print(f"\n[load_test_burn] FAILED {failures} scenario(s)")
        return 1
    print("\n[load_test_burn] all scenarios passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
