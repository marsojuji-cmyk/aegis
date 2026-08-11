"""
Personal usage intelligence — patterns from the durable ledger.

Metrics: reuse rate, cache hit rate, model distribution, project mix,
daily burn, pack efficiency. Feeds forecast + policy_nudges.

Production-hardened: safe coercion, noise filtering (intel_tick), stable shapes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aegis.ledger import filter_week, generate_report, read_all

# Zero-impact bookkeeping kinds — exclude from waste / burn analytics
_NOISE_KINDS = frozenset({"intel_tick", "doctor", "version"})


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _day_key(ts: Optional[str]) -> str:
    dt = _parse_ts(ts)
    if not dt:
        return "unknown"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _is_noise(row: Dict[str, Any]) -> bool:
    kind = str(row.get("kind") or "")
    if kind in _NOISE_KINDS:
        return True
    # pure zero ledger crumbs
    if (
        _safe_int(row.get("raw_in"))
        + _safe_int(row.get("processed_in"))
        + _safe_int(row.get("raw_out"))
        + _safe_int(row.get("processed_out"))
        + _safe_int(row.get("tokens_saved"))
        == 0
        and kind.startswith("intel")
    ):
        return True
    return False


def analyze_usage(
    *,
    week: Optional[str] = None,
    rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Full personal usage profile from ledger (week + lifetime). Always returns a dict."""
    try:
        all_rows = list(rows) if rows is not None else read_all()
    except Exception:  # noqa: BLE001
        all_rows = []

    try:
        report = generate_report(week=week)
    except Exception:  # noqa: BLE001
        report = {
            "week": week or "unknown",
            "total_tokens_saved": 0,
            "total_tokens_consumed": 0,
            "total_raw_tokens_demanded": 0,
            "overall_token_reduction_percent": 0.0,
            "reuse_hit_rate_percent": 0.0,
            "reserve_signal": "ok",
            "remaining_weekly_capacity_percent": 100.0,
            "net_financial_savings_dollars": 0.0,
        }

    week_key = str(report.get("week") or week or "unknown")
    try:
        week_rows = filter_week(all_rows, week_key)
    except Exception:  # noqa: BLE001
        week_rows = []

    signal_rows = [r for r in week_rows if not _is_noise(r)]

    kind_counts = Counter(str(r.get("kind") or "unknown") for r in signal_rows)
    mode_counts = Counter(str(r.get("mode") or "unknown") for r in signal_rows)
    project_counts = Counter(str(r.get("project") or "aegis") for r in signal_rows)

    model_counts: Counter = Counter()
    provider_counts: Counter = Counter()
    for r in signal_rows:
        meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
        prov = meta.get("provider") or meta.get("engine")
        model = meta.get("model")
        if prov:
            provider_counts[str(prov)[:64]] += 1
        if model:
            model_counts[str(model)[:64]] += 1

    packs = [r for r in signal_rows if r.get("kind") in ("pack", "reuse_hit")]
    reuse_hits = sum(
        1 for r in packs if r.get("reuse") or r.get("kind") == "reuse_hit"
    )
    pack_misses = sum(
        1 for r in packs if r.get("kind") == "pack" and not r.get("reuse")
    )
    pack_attempts = reuse_hits + pack_misses
    cache_hit_rate = (
        round((reuse_hits / float(pack_attempts)) * 100.0, 1) if pack_attempts else 0.0
    )

    daily_burn: Dict[str, int] = defaultdict(int)
    daily_saved: Dict[str, int] = defaultdict(int)
    for r in signal_rows:
        d = _day_key(r.get("ts") if isinstance(r.get("ts"), str) else None)
        daily_burn[d] += _safe_int(r.get("processed_in")) + _safe_int(
            r.get("processed_out")
        )
        daily_saved[d] += _safe_int(r.get("tokens_saved"))

    burn_days = [v for k, v in daily_burn.items() if k != "unknown"]
    avg_daily_burn = round(sum(burn_days) / len(burn_days), 1) if burn_days else 0.0
    peak_day = max(burn_days) if burn_days else 0

    raw_total = _safe_int(report.get("total_raw_tokens_demanded"))
    saved = _safe_int(report.get("total_tokens_saved"))
    reduction = _safe_float(report.get("overall_token_reduction_percent"))

    project_types = _infer_project_types(signal_rows)
    team_proxy = {
        "distinct_projects": len(project_counts),
        "mode_diversity": len([m for m, c in mode_counts.items() if c > 0]),
        "estimate": _estimate_team_size(project_counts, mode_counts),
    }

    return {
        "week": week_key,
        "transactions": len(signal_rows),
        "transactions_raw_week": len(week_rows),
        "lifetime_transactions": len(all_rows),
        "kind_distribution": dict(kind_counts.most_common(40)),
        "mode_distribution": dict(mode_counts.most_common(20)),
        "project_distribution": dict(project_counts.most_common(20)),
        "provider_distribution": dict(provider_counts.most_common(20)),
        "model_distribution": dict(model_counts.most_common(15)),
        "reuse_hits": reuse_hits,
        "pack_misses": pack_misses,
        "pack_attempts": pack_attempts,
        "cache_hit_rate_percent": cache_hit_rate,
        "reuse_hit_rate_percent": _safe_float(report.get("reuse_hit_rate_percent")),
        "tokens_saved": saved,
        "tokens_consumed": _safe_int(report.get("total_tokens_consumed")),
        "raw_demanded": raw_total,
        "reduction_percent": reduction,
        "reserve_signal": str(report.get("reserve_signal") or "ok"),
        "remaining_pct": _safe_float(
            report.get("remaining_weekly_capacity_percent"), 100.0
        ),
        "daily_burn": dict(sorted(daily_burn.items())[-14:]),
        "daily_saved": dict(sorted(daily_saved.items())[-14:]),
        "avg_daily_burn": avg_daily_burn,
        "peak_daily_burn": peak_day,
        "project_types": project_types,
        "team_proxy": team_proxy,
        "net_financial_savings_dollars": _safe_float(
            report.get("net_financial_savings_dollars")
        ),
        "noise_filtered": len(week_rows) - len(signal_rows),
    }


def _infer_project_types(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    tags: Counter = Counter()
    for r in rows:
        meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
        paths = meta.get("paths") if isinstance(meta.get("paths"), list) else []
        blob = " ".join(str(p) for p in paths) + " " + str(r.get("task") or "")
        blob_l = blob.lower()
        if any(x in blob_l for x in (".swift", "xcode", "swiftui")):
            tags["swift_macos"] += 1
        if any(x in blob_l for x in (".py", "python", "pytest")):
            tags["python"] += 1
        if any(x in blob_l for x in (".ts", ".tsx", ".js", "react", "node")):
            tags["typescript_js"] += 1
        if any(x in blob_l for x in (".go", "golang")):
            tags["go"] += 1
        if any(x in blob_l for x in (".rs", "rust", "cargo")):
            tags["rust"] += 1
        if any(x in blob_l for x in ("router", "daemon", "api", "http")):
            tags["infra_api"] += 1
        if any(x in blob_l for x in ("test", "spec", "fixture")):
            tags["testing"] += 1
    return dict(tags.most_common(12))


def _estimate_team_size(projects: Counter, modes: Counter) -> str:
    n = len(projects)
    total = sum(modes.values()) if modes else 0
    if n <= 1 and total < 30:
        return "solo"
    if n <= 3:
        return "small"
    if n <= 8:
        return "team"
    return "org"


def waste_signals(usage: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Detect high-ROI correction opportunities. Never raises."""
    try:
        usage = usage if usage is not None else analyze_usage()
    except Exception:  # noqa: BLE001
        return []

    signals: List[Dict[str, Any]] = []
    hit = _safe_float(usage.get("cache_hit_rate_percent"))
    pack_attempts = _safe_int(usage.get("pack_attempts"))
    if pack_attempts >= 5 and hit < 25:
        signals.append(
            {
                "id": "low_cache_hit",
                "severity": "high",
                "title": "Low pack cache hit rate",
                "detail": f"hit_rate={hit}% — normalize modes, reuse path-sets",
                "fix": "boost_cache_fallbacks",
                "expected_savings_tokens": 15_000,
            }
        )

    consumed = _safe_int(usage.get("tokens_consumed"))
    txns = _safe_int(usage.get("transactions"))
    if consumed > 0:
        red = _safe_float(usage.get("reduction_percent"))
        if red < 40 and txns >= 10:
            signals.append(
                {
                    "id": "low_reduction",
                    "severity": "medium",
                    "title": "Token reduction below target",
                    "detail": f"reduction={red}% (aim ≥70%)",
                    "fix": "prefer_explore_and_output_profiles",
                    "expected_savings_tokens": 12_000,
                }
            )

    kinds = usage.get("kind_distribution") or {}
    outs = _safe_int(kinds.get("output_record")) + _safe_int(kinds.get("land"))
    outs += _safe_int(kinds.get("output_estimate"))
    if outs < 3 and txns > 15:
        signals.append(
            {
                "id": "missing_output_land",
                "severity": "medium",
                "title": "Few landed outputs",
                "detail": "Output shrink/store underused — keep land path hot",
                "fix": "enforce_output_land",
                "expected_savings_tokens": 8_000,
            }
        )

    rem = _safe_float(usage.get("remaining_pct"), 100.0)
    signal = str(usage.get("reserve_signal") or "ok")
    if rem < 85 and signal != "ok":
        signals.append(
            {
                "id": "reserve_pressure",
                "severity": "critical",
                "title": "Reserve under pressure",
                "detail": f"remaining={rem}% signal={signal}",
                "fix": "throttle_to_mock_and_reuse",
                "expected_savings_tokens": 20_000,
            }
        )

    modes = usage.get("mode_distribution") or {}
    impl = _safe_int(modes.get("implement"))
    exp = _safe_int(modes.get("explore"))
    if impl > exp * 2 and impl >= 8:
        signals.append(
            {
                "id": "implement_heavy",
                "severity": "low",
                "title": "Implement-heavy mix",
                "detail": "Prefer explore preflight before full implement packs",
                "fix": "default_mode_explore",
                "expected_savings_tokens": 5_000,
            }
        )
    return signals
