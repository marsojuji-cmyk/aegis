"""
Policy nudges — durable config course-correction from waste signals.

Absolute Form constraints:
  - Never lower reserve_floor
  - Never disable autonomy flags here
  - Reinvest rate floor 0.05; never raise risk under pressure
  - Idempotent: same fix id applied at most once per week (caller tracks)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from aegis.config import AegisConfig, load_config, save_config

# Known fix handlers — stable ids match usage_intel.waste_signals
KNOWN_FIXES = frozenset(
    {
        "boost_cache_fallbacks",
        "default_mode_explore",
        "prefer_explore_and_output_profiles",
        "enforce_output_land",
        "throttle_to_mock_and_reuse",
    }
)

REINVEST_FLOOR = 0.05
REINVEST_PRESSURE = 0.10
OUTPUT_MAX_TIGHT = 600


def apply_policy_nudges(
    signals: List[Dict[str, Any]],
    cfg: Optional[AegisConfig] = None,
    *,
    already_applied: Optional[Set[str]] = None,
    persist: bool = True,
) -> Tuple[AegisConfig, List[Dict[str, Any]]]:
    """
    Apply config nudges from waste signals.

    Returns (cfg, applied_list). Skips fix ids in already_applied (weekly set).
    """
    cfg = cfg or load_config()
    if not getattr(cfg, "auto_apply_fixes", True):
        return cfg, []

    seen = set(already_applied or ())
    applied: List[Dict[str, Any]] = []
    changed = False
    # preserve Absolute Form reserve
    original_reserve = float(cfg.reserve_floor)

    for sig in signals or []:
        fix = str(sig.get("fix") or "")
        if not fix or fix not in KNOWN_FIXES:
            continue
        if fix in seen:
            applied.append({"fix": fix, "ok": True, "skipped": "already_applied_this_week"})
            continue

        result: Dict[str, Any] = {"fix": fix, "ok": True, "signal_id": sig.get("id")}

        if fix == "boost_cache_fallbacks":
            result["via"] = "cache_optimizer"
            result["note"] = "cache learn/prune owns this path"
        elif fix == "default_mode_explore":
            if cfg.default_pack_mode != "explore":
                cfg.default_pack_mode = "explore"
                changed = True
                result["default_pack_mode"] = "explore"
            else:
                result["note"] = "already explore"
        elif fix == "prefer_explore_and_output_profiles":
            if cfg.output_default_profile not in ("brief", "diff"):
                cfg.output_default_profile = "brief"
                changed = True
            if int(cfg.output_default_max or 800) > OUTPUT_MAX_TIGHT:
                cfg.output_default_max = OUTPUT_MAX_TIGHT
                changed = True
            result["profile"] = cfg.output_default_profile
            result["max"] = cfg.output_default_max
        elif fix == "enforce_output_land":
            result["note"] = "router land path always on"
        elif fix == "throttle_to_mock_and_reuse":
            rate = float(cfg.reinvest_rate or 0.2)
            if rate > REINVEST_PRESSURE:
                cfg.reinvest_rate = REINVEST_PRESSURE
                changed = True
                result["reinvest_rate"] = REINVEST_PRESSURE
            else:
                result["note"] = f"reinvest already ≤{REINVEST_PRESSURE}"

        # hard guardrails
        if float(cfg.reserve_floor) < original_reserve:
            cfg.reserve_floor = original_reserve
            result["reserve_guard"] = "restored"
        if float(cfg.reinvest_rate) < REINVEST_FLOOR:
            cfg.reinvest_rate = REINVEST_FLOOR
            result["reinvest_guard"] = "floored"

        seen.add(fix)
        applied.append(result)

    if changed and persist:
        save_config(cfg)
        cfg = load_config()

    return cfg, applied


def nudge_summary(applied: List[Dict[str, Any]]) -> str:
    if not applied:
        return "no policy nudges"
    real = [a for a in applied if not a.get("skipped")]
    return f"{len(real)} nudge(s), {len(applied) - len(real)} skipped"
