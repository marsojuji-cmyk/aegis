"""ROI scoring for idea backlog — savings vs effort, with grades."""

from __future__ import annotations

from typing import Any, Dict, Optional

# Confidence multiplies expected savings (uncertain bets score lower).
CONFIDENCE_WEIGHT = {
    "low": 0.5,
    "medium": 0.75,
    "high": 1.0,
}

# Default expected weekly savings by tag when not set on the idea.
TAG_SAVINGS_DEFAULTS = {
    "reuse": 15_000,
    "fidelity": 12_000,
    "e2": 12_000,
    "output": 8_000,
    "e4": 8_000,
    "ux": 4_000,
    "surplus": 2_000,
    "aegis": 5_000,
}


def confidence_weight(confidence: str) -> float:
    return CONFIDENCE_WEIGHT.get(str(confidence).lower(), 0.75)


def infer_expected_savings(idea: Dict[str, Any]) -> int:
    if idea.get("expected_savings_tokens") is not None:
        return max(0, int(idea["expected_savings_tokens"]))
    tags = [str(t).lower() for t in idea.get("tags") or []]
    best = 0
    for t in tags:
        best = max(best, TAG_SAVINGS_DEFAULTS.get(t, 0))
    if best == 0:
        best = TAG_SAVINGS_DEFAULTS["aegis"]
    return best


def effort_tokens(idea: Dict[str, Any]) -> int:
    return max(1, int(idea.get("cost_estimate_tokens") or idea.get("effort_tokens") or 1))


def grade_for_ratio(ratio: float) -> str:
    if ratio >= 5.0:
        return "A"
    if ratio >= 2.0:
        return "B"
    if ratio >= 1.0:
        return "C"
    if ratio >= 0.5:
        return "D"
    return "F"


def score_idea(idea: Dict[str, Any]) -> Dict[str, Any]:
    """
    ROI = (expected_savings * confidence) / effort

    - expected_savings: estimated *recurring weekly* token savings if idea ships
    - effort: cost_estimate_tokens (wish-jar credits / build cost)
    - confidence: low|medium|high
    """
    effort = effort_tokens(idea)
    expected = infer_expected_savings(idea)
    conf = str(idea.get("confidence") or "medium").lower()
    w = confidence_weight(conf)
    risked = expected * w
    ratio = risked / float(effort)
    # 0–100 display score: log-ish so big winners don't explode the scale
    # score = min(100, 20 * log10(1 + ratio * 10)) ≈ ratio 1 → ~26, ratio 5 → ~54, ratio 20 → ~80
    import math

    display = round(min(100.0, 20.0 * math.log10(1.0 + ratio * 10.0)), 1)
    return {
        "effort_tokens": effort,
        "expected_savings_tokens": expected,
        "confidence": conf,
        "confidence_weight": w,
        "roi_ratio": round(ratio, 3),
        "roi_score": display,
        "roi_grade": grade_for_ratio(ratio),
        "payback_weeks": round(effort / max(risked, 1e-9), 2),
    }


def enrich_idea(idea: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of idea with ROI fields attached (non-destructive)."""
    out = dict(idea)
    scored = score_idea(idea)
    out.update(scored)
    # actual ROI if completed with measured savings
    invested = max(1, int(idea.get("funded_credits") or 0) or effort_tokens(idea))
    actual = idea.get("actual_savings_tokens")
    if actual is not None:
        ar = float(actual) / float(invested)
        out["actual_roi_ratio"] = round(ar, 3)
        out["actual_roi_grade"] = grade_for_ratio(ar)
        out["roi_delta"] = round(ar - scored["roi_ratio"], 3)  # positive = beat estimate
    return out


def rank_ideas(ideas: list, *, by: str = "roi_score") -> list:
    enriched = [enrich_idea(i) for i in ideas]
    key = by if by in ("roi_score", "roi_ratio", "expected_savings_tokens", "funded_credits") else "roi_score"
    return sorted(enriched, key=lambda x: float(x.get(key) or 0), reverse=True)
