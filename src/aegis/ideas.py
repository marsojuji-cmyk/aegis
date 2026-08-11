"""Improvement idea backlog funded by surplus credits — with ROI scoring."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aegis.fund import invest_credits, surplus_snapshot
from aegis.ledger import read_all
from aegis.paths import ensure_home, ideas_path
from aegis.roi import enrich_idea, rank_ideas, score_idea


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_ideas() -> List[Dict[str, Any]]:
    path = ideas_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_all(ideas: List[Dict[str, Any]]) -> None:
    ensure_home()
    with ideas_path().open("w", encoding="utf-8") as f:
        for idea in ideas:
            f.write(json.dumps(idea, ensure_ascii=False) + "\n")


def _append(idea: Dict[str, Any]) -> None:
    ensure_home()
    with ideas_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(idea, ensure_ascii=False) + "\n")


def add_idea(
    title: str,
    body: str = "",
    tags: Optional[List[str]] = None,
    cost_estimate_tokens: int = 5000,
    expected_savings_tokens: Optional[int] = None,
    confidence: str = "medium",
    source: str = "user",
) -> Dict[str, Any]:
    idea = {
        "id": f"idea_{uuid.uuid4().hex[:10]}",
        "title": title.strip(),
        "body": body.strip(),
        "tags": tags or ["aegis"],
        "status": "queued",
        "cost_estimate_tokens": int(cost_estimate_tokens),
        "expected_savings_tokens": (
            int(expected_savings_tokens) if expected_savings_tokens is not None else None
        ),
        "confidence": confidence.lower() if confidence else "medium",
        "funded_credits": 0,
        "actual_savings_tokens": None,
        "completed_ts": None,
        "created_ts": _now(),
        "source": source,
    }
    # Persist computed defaults so list is stable without re-infer
    scored = score_idea(idea)
    if idea["expected_savings_tokens"] is None:
        idea["expected_savings_tokens"] = scored["expected_savings_tokens"]
    idea["roi_ratio"] = scored["roi_ratio"]
    idea["roi_score"] = scored["roi_score"]
    idea["roi_grade"] = scored["roi_grade"]
    _append(idea)
    return enrich_idea(idea)


def list_ideas(
    status: Optional[str] = None,
    *,
    by_roi: bool = True,
) -> List[Dict[str, Any]]:
    ideas = _read_ideas()
    if status:
        ideas = [i for i in ideas if i.get("status") == status]
    if by_roi:
        return rank_ideas(ideas, by="roi_score")
    return [enrich_idea(i) for i in ideas]


def get_idea(idea_id: str) -> Optional[Dict[str, Any]]:
    for i in _read_ideas():
        if i.get("id") == idea_id:
            return enrich_idea(i)
    return None


def invest_in_idea(idea_id: str, credits: Optional[int] = None) -> Dict[str, Any]:
    ideas = _read_ideas()
    idea = None
    idx = -1
    for i, row in enumerate(ideas):
        if row.get("id") == idea_id:
            idea = row
            idx = i
            break
    if idea is None:
        return {"ok": False, "error": f"unknown idea {idea_id}"}

    amount = credits if credits is not None else int(idea.get("cost_estimate_tokens", 0))
    if amount <= 0:
        amount = 1000

    result = invest_credits(amount)
    if not result.get("ok"):
        return result

    idea["funded_credits"] = int(idea.get("funded_credits", 0)) + amount
    if idea.get("status") == "queued":
        idea["status"] = "funded"
    # refresh ROI snapshot on write
    scored = score_idea(idea)
    idea["roi_ratio"] = scored["roi_ratio"]
    idea["roi_score"] = scored["roi_score"]
    idea["roi_grade"] = scored["roi_grade"]
    ideas[idx] = idea
    _write_all(ideas)
    return {
        "ok": True,
        "idea": enrich_idea(idea),
        "invested": amount,
        "available_credits": result["available_credits"],
    }


def complete_idea(
    idea_id: str,
    actual_savings_tokens: int,
    note: str = "",
) -> Dict[str, Any]:
    """Mark idea done and record measured savings for the learning loop."""
    ideas = _read_ideas()
    idx = -1
    idea = None
    for i, row in enumerate(ideas):
        if row.get("id") == idea_id:
            idea = row
            idx = i
            break
    if idea is None:
        return {"ok": False, "error": f"unknown idea {idea_id}"}

    idea["status"] = "done"
    idea["actual_savings_tokens"] = int(actual_savings_tokens)
    idea["completed_ts"] = _now()
    if note:
        meta = idea.get("meta") or {}
        meta["complete_note"] = note
        idea["meta"] = meta
    ideas[idx] = idea
    _write_all(ideas)
    enriched = enrich_idea(idea)
    return {"ok": True, "idea": enriched}


def update_idea_roi(
    idea_id: str,
    *,
    expected_savings_tokens: Optional[int] = None,
    cost_estimate_tokens: Optional[int] = None,
    confidence: Optional[str] = None,
) -> Dict[str, Any]:
    ideas = _read_ideas()
    for i, row in enumerate(ideas):
        if row.get("id") != idea_id:
            continue
        if expected_savings_tokens is not None:
            row["expected_savings_tokens"] = int(expected_savings_tokens)
        if cost_estimate_tokens is not None:
            row["cost_estimate_tokens"] = int(cost_estimate_tokens)
        if confidence is not None:
            row["confidence"] = confidence.lower()
        scored = score_idea(row)
        row["roi_ratio"] = scored["roi_ratio"]
        row["roi_score"] = scored["roi_score"]
        row["roi_grade"] = scored["roi_grade"]
        ideas[i] = row
        _write_all(ideas)
        return {"ok": True, "idea": enrich_idea(row)}
    return {"ok": False, "error": f"unknown idea {idea_id}"}


def seed_starter_ideas() -> List[Dict[str, Any]]:
    """Idempotent starter backlog for Aegis self-improvement."""
    existing = {i.get("title") for i in _read_ideas()}
    # title, body, tags, effort, expected_weekly_savings, confidence
    starters = [
        (
            "E2 safe implement-mode pack fidelity",
            "Never skeleton-only on implement; full target bodies + neighbor signatures.",
            ["aegis", "e2", "fidelity"],
            8000,
            20_000,
            "high",
        ),
        (
            "Wire output profiles into aegis-tokenomics skill",
            "Skill should call `aegis output --profile diff|brief` and record-out when known.",
            ["aegis", "e4", "output"],
            3000,
            10_000,
            "medium",
        ),
        (
            "Pack cache hit-rate dashboard in budget",
            "Surface reuse_hits and hit rate so surplus compounds visibly.",
            ["aegis", "reuse", "ux"],
            2000,
            6_000,
            "high",
        ),
    ]
    created = []
    for title, body, tags, cost, savings, conf in starters:
        if title in existing:
            continue
        created.append(
            add_idea(
                title,
                body=body,
                tags=tags,
                cost_estimate_tokens=cost,
                expected_savings_tokens=savings,
                confidence=conf,
                source="auto",
            )
        )
    return created


def rescore_all() -> int:
    """Recompute and persist ROI fields for every idea (migration helper)."""
    ideas = _read_ideas()
    if not ideas:
        return 0
    for i, row in enumerate(ideas):
        scored = score_idea(row)
        if row.get("expected_savings_tokens") is None:
            row["expected_savings_tokens"] = scored["expected_savings_tokens"]
        if not row.get("confidence"):
            row["confidence"] = scored["confidence"]
        row["roi_ratio"] = scored["roi_ratio"]
        row["roi_score"] = scored["roi_score"]
        row["roi_grade"] = scored["roi_grade"]
        ideas[i] = row
    _write_all(ideas)
    return len(ideas)


def suggest_ideas() -> List[Dict[str, Any]]:
    """Heuristic suggestions from ledger patterns (not LLM)."""
    rows = read_all()
    suggestions: List[Dict[str, Any]] = []
    packs = [r for r in rows if r.get("kind") in ("pack", "reuse_hit")]
    reuses = sum(1 for r in packs if r.get("reuse") or r.get("kind") == "reuse_hit")
    if packs and reuses / max(len(packs), 1) < 0.2:
        suggestions.append(
            {
                "title": "Increase pack reuse (same-mode workflows)",
                "body": "Low cache hit rate — prefer repeated pack keys / stable tasks.",
                "tags": ["aegis", "reuse"],
                "expected_savings_tokens": 15_000,
                "cost_estimate_tokens": 2000,
                "confidence": "medium",
                "source": "surplus_suggest",
            }
        )
    outs = [r for r in rows if r.get("kind") in ("output_estimate", "output_record")]
    if len(outs) < 3 and len(rows) > 5:
        suggestions.append(
            {
                "title": "Start recording output savings",
                "body": "Few output txns — use `aegis output` + `record-out` to cut reply waste.",
                "tags": ["aegis", "output"],
                "expected_savings_tokens": 8_000,
                "cost_estimate_tokens": 1500,
                "confidence": "high",
                "source": "surplus_suggest",
            }
        )
    snap = surplus_snapshot()
    if snap["reserve_signal"] == "ok" and snap["available_credits"] > 0:
        ranked = list_ideas(status="queued")
        if ranked:
            top = ranked[0]
            suggestions.append(
                {
                    "title": f"Invest in highest-ROI idea: {top.get('title')}",
                    "body": (
                        f"grade={top.get('roi_grade')} score={top.get('roi_score')} "
                        f"ratio={top.get('roi_ratio')} — {snap['available_credits']} credits free"
                    ),
                    "tags": ["aegis", "surplus"],
                    "source": "surplus_suggest",
                    "idea_id": top.get("id"),
                }
            )
        else:
            suggestions.append(
                {
                    "title": "Invest surplus into next fidelity epoch",
                    "body": f"{snap['available_credits']} credits available — add a high-ROI idea.",
                    "tags": ["aegis", "surplus"],
                    "source": "surplus_suggest",
                }
            )
    if not suggestions:
        suggestions.append(
            {
                "title": "Keep packing — grow the wish jar",
                "body": "No strong waste pattern yet. Run pack/scrub; reinvest when credits appear.",
                "tags": ["aegis"],
                "source": "surplus_suggest",
            }
        )
    # attach ROI preview for suggestions that have numbers
    out = []
    for s in suggestions:
        if s.get("expected_savings_tokens") and s.get("cost_estimate_tokens"):
            out.append(enrich_idea(s))
        else:
            out.append(s)
    return out
