"""Investment audit — review funded ideas and learn from outcomes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aegis.ideas import list_ideas
from aegis.roi import enrich_idea


def audit_portfolio() -> Dict[str, Any]:
    """
    Review all ideas with funding or completion status.
    Produces portfolio metrics + per-idea learning rows + lessons.
    """
    all_ideas = [enrich_idea(i) for i in list_ideas()]
    invested = [
        i
        for i in all_ideas
        if int(i.get("funded_credits") or 0) > 0
        or i.get("status") in ("funded", "active", "done")
    ]
    done = [i for i in all_ideas if i.get("status") == "done"]
    measured = [i for i in done if i.get("actual_savings_tokens") is not None]

    total_invested = sum(int(i.get("funded_credits") or 0) for i in invested)
    total_expected = sum(int(i.get("expected_savings_tokens") or 0) for i in invested)
    total_actual = sum(int(i.get("actual_savings_tokens") or 0) for i in measured)

    # Portfolio predicted ROI (on funded set)
    portfolio_expected_ratio = (
        round(total_expected / float(total_invested), 3) if total_invested else 0.0
    )
    portfolio_actual_ratio = (
        round(total_actual / float(max(1, sum(int(i.get("funded_credits") or 0) for i in measured))), 3)
        if measured
        else None
    )

    winners = [
        i
        for i in measured
        if float(i.get("actual_roi_ratio") or 0) >= float(i.get("roi_ratio") or 0)
    ]
    losers = [
        i
        for i in measured
        if float(i.get("actual_roi_ratio") or 0) < float(i.get("roi_ratio") or 0)
    ]
    unmeasured_done = [i for i in done if i.get("actual_savings_tokens") is None]
    funded_not_done = [
        i for i in invested if i.get("status") in ("funded", "active")
    ]

    lessons: List[str] = []
    if not invested:
        lessons.append("No investments yet — fund a high-ROI queued idea when reserve is ok.")
    if funded_not_done:
        lessons.append(
            f"{len(funded_not_done)} funded idea(s) not marked done — ship or close them."
        )
    if unmeasured_done:
        lessons.append(
            f"{len(unmeasured_done)} done without actual_savings — "
            "run: aegis idea complete <id> --actual-savings N"
        )
    if measured and portfolio_actual_ratio is not None:
        if portfolio_actual_ratio >= portfolio_expected_ratio:
            lessons.append(
                f"Portfolio beating estimates (actual ROI {portfolio_actual_ratio} "
                f"vs expected {portfolio_expected_ratio}). Double down on similar grades."
            )
        else:
            lessons.append(
                f"Portfolio under expected ROI (actual {portfolio_actual_ratio} "
                f"vs expected {portfolio_expected_ratio}). Prefer higher confidence / lower effort."
            )
    if winners:
        titles = ", ".join(w["title"][:40] for w in winners[:3])
        lessons.append(f"Winners (met/beat estimate): {titles}")
    if losers:
        titles = ", ".join(l["title"][:40] for l in losers[:3])
        lessons.append(f"Misses (below estimate): {titles} — lower future confidence on similar tags.")
    if not measured and invested:
        lessons.append(
            "Learning loop incomplete: complete ideas with measured savings to calibrate ROI."
        )

    # Rank remaining queued by ROI for next invest recommendation
    queued = [i for i in all_ideas if i.get("status") == "queued"]
    queued_ranked = sorted(queued, key=lambda x: float(x.get("roi_score") or 0), reverse=True)
    next_pick = queued_ranked[0] if queued_ranked else None

    return {
        "summary": {
            "ideas_total": len(all_ideas),
            "invested_count": len(invested),
            "done_count": len(done),
            "measured_count": len(measured),
            "total_credits_invested": total_invested,
            "total_expected_weekly_savings": total_expected,
            "total_actual_savings_recorded": total_actual,
            "portfolio_expected_roi_ratio": portfolio_expected_ratio,
            "portfolio_actual_roi_ratio": portfolio_actual_ratio,
            "winners": len(winners),
            "misses": len(losers),
        },
        "investments": invested,
        "next_best_queued": next_pick,
        "lessons": lessons,
    }


def format_audit_text(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "Aegis investment audit",
        f"  ideas:        {s['ideas_total']} total, {s['invested_count']} funded, "
        f"{s['done_count']} done, {s['measured_count']} measured",
        f"  invested:     {s['total_credits_invested']:,} credits",
        f"  expected Δ:   ~{s['total_expected_weekly_savings']:,} tok/week (if all ship)",
        f"  actual Δ:     {s['total_actual_savings_recorded']:,} tok recorded on done",
        f"  portfolio ROI expected: {s['portfolio_expected_roi_ratio']}",
        f"  portfolio ROI actual:   {s['portfolio_actual_roi_ratio'] if s['portfolio_actual_roi_ratio'] is not None else 'n/a (measure done ideas)'}",
        f"  winners/misses: {s['winners']}/{s['misses']}",
        "",
        "Investments:",
    ]
    inv = report.get("investments") or []
    if not inv:
        lines.append("  (none yet)")
    for i in inv:
        actual = i.get("actual_savings_tokens")
        actual_s = (
            f"actual={actual} ROI={i.get('actual_roi_ratio')}({i.get('actual_roi_grade')})"
            if actual is not None
            else "actual=unmeasured"
        )
        lines.append(
            f"  {i['id']} [{i.get('status')}] grade={i.get('roi_grade')} "
            f"score={i.get('roi_score')} funded={i.get('funded_credits', 0)} "
            f"exp={i.get('expected_savings_tokens')} {actual_s}"
        )
        lines.append(f"      {i.get('title')}")

    nxt = report.get("next_best_queued")
    lines.append("")
    if nxt:
        lines.append(
            f"Next best by ROI: {nxt['id']} grade={nxt.get('roi_grade')} "
            f"score={nxt.get('roi_score')} — {nxt.get('title')}"
        )
        lines.append(f"  invest hint: aegis invest {nxt['id']} --credits {min(500, int(nxt.get('effort_tokens') or 500))}")
    else:
        lines.append("Next best by ROI: (no queued ideas)")

    lines.append("")
    lines.append("Lessons:")
    for lesson in report.get("lessons") or []:
        lines.append(f"  • {lesson}")
    return "\n".join(lines)
