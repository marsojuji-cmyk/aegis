"""Honest AGIS/Aegis product pricing.

Replacement-cost + completeness. Token-bill dollars are a demo, not the price.
`savings_percent` stays null. Hosted SaaS is not a SKU.
"""

from __future__ import annotations

from typing import Any, Dict, List

from aegis import __version__
from aegis.config import load_config
from aegis.kernel import scorecard
from aegis.ledger import generate_report

# First OS evaluation on this track (agent-OS rubric, not Darwin).
THEN: Dict[str, Any] = {
    "when": "2026-08-18 pre-1.2.0",
    "composite": 4.2,
    "sellable": False,
    "advice": "do_not_sell",
    "layers": {
        "kernel": 0,
        "control_plane": 7,
        "persistence": 6,
        "install_multiuser": 1,
        "public_api": 4,
        "proven_yield": 3,
    },
    "source_usd": {"low": 25000, "high": 45000},
    "exclusive_usd": {"low": 80000, "high": 120000},
    "note": "Sticker existed. Portable home, frozen /v1, and second-machine doctor did not.",
}

REPLACEMENT_HOURS = 400
REPLACEMENT_RATE_USD = 250
REUSE_TARGET_PCT = 50.0

# Observed Nous/xiaomi pairs from authorized health runs. Estimated USD. Not admitted.
OBSERVED_PAIRS: List[Dict[str, Any]] = [
    {
        "file": "src/aegis/cli.py",
        "naive_usd": 0.00987,
        "packed_usd": 0.00131,
        "delta_usd": 0.00856,
        "cost_status": "estimated",
    },
    {
        "file": "src/aegis/budget_aware.py",
        "naive_usd": 0.00910,
        "packed_usd": 0.00071,
        "delta_usd": 0.00838,
        "cost_status": "estimated",
    },
]


def _mid(band: Dict[str, int]) -> int:
    return int(round((int(band["low"]) + int(band["high"])) / 2.0))


def _round_money(n: float) -> int:
    return int(round(n / 1000.0) * 1000)


def quote() -> Dict[str, Any]:
    """Live quote. Completeness can raise the band; token $ cannot."""
    card = scorecard()
    report = generate_report()
    cfg = load_config()
    composite = float(card.get("composite") or 0)
    reuse = float(report.get("reuse_hit_rate_percent") or 0)
    remaining = float(report.get("remaining_weekly_capacity_percent") or 0)
    local_saved = int(report.get("total_tokens_saved") or 0)
    from aegis.doctor import doctor_report

    ready = bool((doctor_report() or {}).get("product_ready"))
    cost_per_1k = float(getattr(cfg, "cost_per_1k_input", 0.00125) or 0.00125)
    # Ledger saved tokens × local counterfactual rate. Not provider USD.
    week_token_usd = round((local_saved / 1000.0) * cost_per_1k, 4)

    replacement = REPLACEMENT_HOURS * REPLACEMENT_RATE_USD
    completeness = max(0.0, min(1.0, (composite - THEN["composite"]) / (10.0 - THEN["composite"])))
    premium = 40000.0 * completeness
    yield_haircut = 15000.0 * ((10.0 - float((card.get("layers") or {}).get("proven_yield", {}).get("score") or 8)) / 10.0)
    reuse_haircut = 10000.0 * max(0.0, (REUSE_TARGET_PCT - reuse) / REUSE_TARGET_PCT)
    exclusive_mid = _round_money(THEN["exclusive_usd"]["low"] + premium - yield_haircut - reuse_haircut)
    exclusive_mid = max(THEN["exclusive_usd"]["low"], min(150000, exclusive_mid))
    exclusive = {
        "low": _round_money(exclusive_mid * 0.85),
        "mid": exclusive_mid,
        "high": _round_money(exclusive_mid * 1.15),
    }
    source_mid = _round_money(exclusive_mid * 0.42)
    source = {
        "low": _round_money(source_mid * 0.85),
        "mid": source_mid,
        "high": _round_money(source_mid * 1.15),
    }

    then_ex_mid = _mid(THEN["exclusive_usd"])
    then_src_mid = _mid(THEN["source_usd"])
    pair_delta = round(sum(float(p["delta_usd"]) for p in OBSERVED_PAIRS), 5)
    now_layers = {
        name: int((card.get("layers") or {}).get(name, {}).get("score") or 0)
        for name in THEN["layers"]
    }
    return {
        "ok": True,
        "version": __version__,
        "savings_percent": None,
        "accounting": "replacement_cost_plus_completeness",
        "sku": "AGIS/Aegis 1.2.0 local agent OS",
        "not": [
            "host kernel",
            "hosted SaaS",
            "consumer marketplace",
            "claimed model-savings product",
        ],
        "then": dict(THEN),
        "now": {
            "composite": composite,
            "sellable": ready,
            "advice": "sell_as_local_program" if ready else "do_not_sell",
            "layers": now_layers,
            "reuse_hit_rate_percent": reuse,
            "remaining_pct": remaining,
            "product_ready": ready,
        },
        "value_delta": {
            "composite_points": round(composite - THEN["composite"], 1),
            "sellable_then": False,
            "sellable_now": ready,
            "exclusive_mid_usd_then": then_ex_mid,
            "exclusive_mid_usd_now": exclusive["mid"],
            "exclusive_mid_delta_usd": exclusive["mid"] - then_ex_mid,
            "source_mid_usd_then": then_src_mid,
            "source_mid_usd_now": source["mid"],
            "note": "The jump is sellability (install/API/portable at 10). Price is not 10x. Yield is still 8/10.",
        },
        "replacement": {
            "hours": REPLACEMENT_HOURS,
            "rate_usd": REPLACEMENT_RATE_USD,
            "usd": replacement,
            "note": "Specialist rebuild of this program, not a SaaS valuation.",
        },
        "skus": {
            "source_nonexclusive": {
                "usd": source,
                "includes": "source, one lab, freeze list as warranty, no SLA",
            },
            "exclusive_lab_12mo": {
                "usd": exclusive,
                "includes": "exclusivity 12 months, source, freeze list as contract, no hosted clause",
            },
            "hosted_saas": {
                "usd": None,
                "includes": "not offered",
            },
        },
        "token_demo": {
            "savings_percent": None,
            "week_local_saved_tokens": local_saved,
            "week_local_usd_counterfactual": week_token_usd,
            "cost_per_1k_input": cost_per_1k,
            "observed_pairs": OBSERVED_PAIRS,
            "observed_pair_delta_usd": pair_delta,
            "note": "Provider-estimated pair USD is a demo. Do not price the program off the API bill.",
        },
        "buyer": {
            "yes": "operators already paying Cursor/Hermes who need a second-machine control plane and receipts",
            "no": "CFOs buying 10x LLM savings, VCs wanting an AI OS, anyone asking for hosted multi-tenant",
        },
        "sell": [
            "Qualify: local agents, not SaaS.",
            "Demo: aegis os init → pack the same files twice → aegis os ready → yield report (null).",
            "Show one naive-vs-pack estimated USD on their file. Do not quote savings_percent.",
            "Contract the freeze list as warranty (no auto-invest, no hosted, no fake yield).",
            "Close source vs exclusive. Walk if they want a marketplace.",
        ],
        "market": [
            "Sentence: local agent control plane that packs, gates, and refuses fake savings.",
            "Allowed: agent-OS scores, os ready, named-file estimated pair USD, freeze list.",
            "Forbidden: Darwin replacement, savings_percent, 10x product, hosted SKU.",
            "Channel: direct to operator-owners. No ads. One demo repo.",
        ],
    }


def format_quote(q: Dict[str, Any]) -> str:
    sk = q["skus"]
    src = sk["source_nonexclusive"]["usd"]
    ex = sk["exclusive_lab_12mo"]["usd"]
    d = q["value_delta"]
    demo = q["token_demo"]
    lines = [
        f"Aegis price  v{q.get('version')}  sku={q.get('sku')}",
        f"  then  composite={q['then']['composite']} sellable=false  source=${THEN['source_usd']['low']:,}–{THEN['source_usd']['high']:,}  exclusive=${THEN['exclusive_usd']['low']:,}–{THEN['exclusive_usd']['high']:,}  advice=do_not_sell",
        f"  now   composite={q['now']['composite']} sellable=true   source=${src['low']:,}–{src['high']:,} (mid ${src['mid']:,})  exclusive=${ex['low']:,}–{ex['high']:,} (mid ${ex['mid']:,})",
        f"  delta composite +{d['composite_points']}  exclusive mid ${d['exclusive_mid_usd_then']:,}→${d['exclusive_mid_usd_now']:,} ({d['exclusive_mid_delta_usd']:+,})",
        f"  replacement {q['replacement']['hours']}h × ${q['replacement']['rate_usd']}/h = ${q['replacement']['usd']:,}",
        f"  token demo  week local ${demo['week_local_usd_counterfactual']} on {demo['week_local_saved_tokens']:,} tok  pair Δ ${demo['observed_pair_delta_usd']} estimated  savings_percent=null",
        f"  buyer  {q['buyer']['yes']}",
        "  not a SKU: hosted SaaS",
    ]
    return "\n".join(lines)
