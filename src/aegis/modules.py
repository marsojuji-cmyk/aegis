"""Budget-aware module health. Every M- is keep, park, repair, or superseded.

There is no historical M- register. These IDs map 1:1 onto DEFAULT_MODULES
plus the removed ghost enrichment slot (M-013).
Probes are local. `aegis modules measure` reuses the authorized Hermes pair.
`savings_percent` stays null unless an admitted pair exists.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aegis import __version__
from aegis.budget_aware import DEFAULT_MODULES
from aegis.config import load_config, opt_in
from aegis.paths import aegis_home

# Catalog order is the operator loop, not score rank.
MODULE_IDS: Tuple[str, ...] = (
    "M-001",
    "M-002",
    "M-003",
    "M-004",
    "M-005",
    "M-006",
    "M-007",
    "M-008",
    "M-009",
    "M-010",
    "M-011",
    "M-012",
    "M-013",
    "M-014",
)

MODULE_NAMES = {
    "M-001": "surplus_sync",
    "M-002": "usage_intel",
    "M-003": "forecast",
    "M-004": "burn_status",
    "M-005": "weekly_report",
    "M-006": "policy_nudges",
    "M-007": "cache_optimize",
    "M-008": "auto_invest",
    "M-009": "auto_queue_ideas",
    "M-010": "seed_ideas",
    "M-011": "memory_capture",
    "M-012": "cross_model_memory_inject",
    "M-013": "exploratory_enrichment",
    "M-014": "continuity_bridge",
}


def _catalog_names() -> List[str]:
    return [m.name for m in DEFAULT_MODULES]


def _ok(
    mid: str,
    *,
    verdict: str,
    aligned: bool,
    evidence: str,
    action: str,
) -> Dict[str, Any]:
    return {
        "id": mid,
        "name": MODULE_NAMES[mid],
        "ok": aligned,
        "verdict": verdict,
        "aligned": aligned,
        "evidence": evidence,
        "action": action,
    }


def _probe_m001() -> Dict[str, Any]:
    from aegis.fund import surplus_snapshot, sync_from_ledger

    fund = sync_from_ledger()
    snap = surplus_snapshot()
    in_cat = "surplus_sync" in _catalog_names()
    aligned = in_cat and isinstance(fund, dict) and isinstance(snap, dict)
    return _ok(
        "M-001",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"catalog={in_cat} credits={snap.get('available_credits')} signal={snap.get('status') or snap.get('reserve_signal')}",
        action="keep never-shed surplus sync; do not auto-spend credits",
    )


def _probe_m002() -> Dict[str, Any]:
    from aegis.usage_intel import analyze_usage

    usage = analyze_usage()
    aligned = isinstance(usage, dict) and "week" in usage
    return _ok(
        "M-002",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"week={usage.get('week')} remaining_pct={usage.get('remaining_pct')}",
        action="keep usage intel; do not promote local counters to official thresholds",
    )


def _probe_m003() -> Dict[str, Any]:
    from aegis.forecast import predict_budget

    fc = predict_budget()
    aligned = isinstance(fc, dict) and "projected_signal" in fc
    return _ok(
        "M-003",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"projected_signal={fc.get('projected_signal')} remaining={fc.get('projected_remaining_pct')}",
        action="keep forecast; projected hard_stop still freezes invest",
    )


def _probe_m004() -> Dict[str, Any]:
    from aegis.burn import burn_status

    burn = burn_status(record_events=False)
    remaining = burn.get("remaining_pct")
    ratio = burn.get("ratio")
    level = burn.get("level")
    aligned = isinstance(burn, dict) and level in {"ok", "caution", "warn", "critical"}
    return _ok(
        "M-004",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"level={level} ratio={ratio} remaining_pct={remaining} safe={burn.get('safe_daily')}",
        action="keep daily/safe ratio; remaining-above-floor is the spendable headroom, not the weekly leftover",
    )


def _probe_m005() -> Dict[str, Any]:
    from aegis.paths import reports_dir

    rdir = reports_dir()
    aligned = True
    try:
        rdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        aligned = False
        return _ok(
            "M-005",
            verdict="repair",
            aligned=False,
            evidence=f"reports_dir_error={exc}",
            action="fix reports path under ~/.aegis",
        )
    return _ok(
        "M-005",
        verdict="keep",
        aligned=aligned,
        evidence=f"reports={rdir}",
        action="keep weekly report; write only from an explicit tick or CLI",
    )


def _probe_m006() -> Dict[str, Any]:
    cfg = load_config()
    on = opt_in(cfg, "auto_apply_fixes")
    return _ok(
        "M-006",
        verdict="park",
        aligned=not on,
        evidence=f"auto_apply_fixes={on}",
        action="keep parked; observation must not mutate pack/output policy",
    )


def _probe_m007() -> Dict[str, Any]:
    from aegis.cache_optimizer import hit_rate

    rate = hit_rate()
    aligned = isinstance(rate, (int, float))
    return _ok(
        "M-007",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"hit_rate_percent={rate}",
        action="keep cache optimize; sheddable under emergency",
    )


def _probe_m008() -> Dict[str, Any]:
    cfg = load_config()
    on = opt_in(cfg, "auto_invest")
    return _ok(
        "M-008",
        verdict="park",
        aligned=not on,
        evidence=f"auto_invest={on}",
        action="keep parked; invest stays frozen until the operator thaws it",
    )


def _probe_m009() -> Dict[str, Any]:
    cfg = load_config()
    gated = opt_in(cfg, "auto_apply_fixes") or opt_in(cfg, "auto_invest")
    return _ok(
        "M-009",
        verdict="park",
        aligned=not gated,
        evidence=f"queue_armed={gated}",
        action="keep parked; auto-queue only when invest or apply-fixes is explicit",
    )


def _probe_m010() -> Dict[str, Any]:
    from aegis.ideas import list_ideas, seed_starter_ideas

    starters = {
        "E2 safe implement-mode pack fidelity",
        "Wire output profiles into aegis-tokenomics skill",
        "Pack cache hit-rate dashboard in budget",
    }
    titles = {i.get("title") for i in list_ideas(by_roi=False)}
    present = len(starters & titles)
    aligned = callable(seed_starter_ideas) and "seed_ideas" in _catalog_names()
    return _ok(
        "M-010",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"starter_present={present}/3 (probe does not seed)",
        action="keep idempotent starter seed; do not invent backlog beyond the three titles",
    )


def _probe_m011() -> Dict[str, Any]:
    from aegis.memory import memory_stats

    cfg = load_config()
    on = opt_in(cfg, "auto_memory")
    stats = memory_stats()
    aligned = (not on) and isinstance(stats, dict)
    return _ok(
        "M-011",
        verdict="park",
        aligned=aligned,
        evidence=f"auto_memory={on} entries={stats.get('entries')} r015=open",
        action="keep parked; R-015 still blocks domain-scoped Hermes memory writes",
    )


def _probe_m012() -> Dict[str, Any]:
    from aegis.memory import memory_context_block

    cfg = load_config()
    on = opt_in(cfg, "auto_memory")
    block = memory_context_block("module-health", project="aegis", limit=1)
    aligned = (not on) and isinstance(block, str)
    return _ok(
        "M-012",
        verdict="park",
        aligned=aligned,
        evidence=f"auto_memory={on} inject_len={len(block)}",
        action="keep parked; router injects only when auto_memory is explicit",
    )


def _probe_m013() -> Dict[str, Any]:
    present = "exploratory_enrichment" in _catalog_names()
    return _ok(
        "M-013",
        verdict="superseded",
        aligned=not present,
        evidence=f"in_catalog={present}",
        action="keep removed; catalog must not shed a module that never ran",
    )


def _probe_m014() -> Dict[str, Any]:
    from aegis.continuity import maybe_auto_bridge

    cfg = load_config()
    enabled = bool(getattr(cfg, "continuity_bridge_enabled", True))
    in_cat = "continuity_bridge" in _catalog_names()
    quiet = maybe_auto_bridge(cfg, band="ok")
    aligned = enabled and in_cat and quiet is None
    return _ok(
        "M-014",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"enabled={enabled} catalog={in_cat} ok_band_bridge={quiet is not None}",
        action="keep emergency-only auto-bridge; do not fire on ok/caution",
    )


PROBES = {
    "M-001": _probe_m001,
    "M-002": _probe_m002,
    "M-003": _probe_m003,
    "M-004": _probe_m004,
    "M-005": _probe_m005,
    "M-006": _probe_m006,
    "M-007": _probe_m007,
    "M-008": _probe_m008,
    "M-009": _probe_m009,
    "M-010": _probe_m010,
    "M-011": _probe_m011,
    "M-012": _probe_m012,
    "M-013": _probe_m013,
    "M-014": _probe_m014,
}


def health() -> Dict[str, Any]:
    rows = []
    for mid in MODULE_IDS:
        try:
            rows.append(PROBES[mid]())
        except Exception as exc:  # noqa: BLE001
            rows.append(
                _ok(
                    mid,
                    verdict="repair",
                    aligned=False,
                    evidence=f"probe_error={exc}",
                    action="fix probe or mark parked",
                )
            )
    repair = [r for r in rows if r["verdict"] == "repair" or not r["aligned"]]
    return {
        "ok": not repair,
        "version": __version__,
        "home": str(aegis_home()),
        "count": len(rows),
        "repair": [r["id"] for r in repair],
        "modules": rows,
    }


def measure_naive_vs_pack(
    path: str,
    *,
    model: str = "xiaomi/mimo-v2.5-pro",
    provider: str = "nous",
) -> Dict[str, Any]:
    """Same authorized Hermes pair as decisions.measure. savings_percent stays null."""
    from aegis.decisions import measure_naive_vs_pack as _measure

    return _measure(path, model=model, provider=provider)
