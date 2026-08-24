"""Durable evidence-to-yield loop for bounded GrokBot/Hermes decisions."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from aegis.grokbots import (
    circuit_breaker,
    quarantine_evidence,
    source_reliability,
    validate_claim,
)
from aegis.paths import aegis_home, ensure_home

_LOCK = threading.RLock()
OBSERVED_COST = "provider_observed"
UNKNOWN_COST = "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def evidence_yield_path() -> Path:
    ensure_home()
    return aegis_home() / "evidence_yield.jsonl"


def _append(event: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(event)
    row.setdefault("id", str(uuid.uuid4()))
    row.setdefault("timestamp", _now())
    with _LOCK:
        with evidence_yield_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def load_events() -> List[Dict[str, Any]]:
    path = evidence_yield_path()
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("event"):
            rows.append(row)
    return rows


def govern_claim(
    *, candidate_id: str, claim: str, evidence: Iterable[Dict[str, Any]],
    impact: str = "low", active_outcome: str = "", provider: str = "",
    model: str = "", request_id: str = ""
) -> Dict[str, Any]:
    """Hermes admission gate: persist evidence, quarantine, then decide."""
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id:
        raise ValueError("candidate_id is required")
    evidence_rows = list(evidence)
    partition = quarantine_evidence(evidence_rows)
    decision = validate_claim(claim, partition["accepted"], impact=impact)
    metadata = {
        "candidate_id": candidate_id,
        "claim": decision["claim"],
        "impact": decision["impact"],
        "active_outcome": str(active_outcome or "").strip(),
        "provider": str(provider or "").strip(),
        "model": str(model or "").strip(),
        "request_id": str(request_id or "").strip(),
    }
    for item in partition["accepted"]:
        _append({"event": "evidence_admitted", **metadata, "evidence": item})
    for item in partition["quarantined"]:
        _append({"event": "evidence_quarantined", **metadata, **item})
    recorded = _append({"event": "claim_decision", **metadata, "decision": decision})
    return {
        "decision_id": recorded["id"],
        "decision": decision,
        "admitted_evidence": len(partition["accepted"]),
        "quarantined_evidence": len(partition["quarantined"]),
        "outreach_authorized": False,
    }


def record_verified_outcome(
    *, candidate_id: str, domain: str, verified: bool, accepted: bool,
    review_minutes: float, correction_minutes: float = 0.0,
    cost_usd: Optional[float] = None, cost_status: str = UNKNOWN_COST,
    cost_source: str = "", request_id: str = ""
) -> Dict[str, Any]:
    """Record a later human/observed outcome without inventing ROI evidence."""
    status = str(cost_status or UNKNOWN_COST).strip()
    if status not in {UNKNOWN_COST, OBSERVED_COST}:
        raise ValueError("cost_status must be unknown or provider_observed")
    if status == OBSERVED_COST and (cost_usd is None or not cost_source or not request_id):
        raise ValueError("provider_observed cost requires cost_usd, cost_source, and request_id")
    if status == UNKNOWN_COST and (cost_usd is not None or cost_source or request_id):
        raise ValueError("unknown cost cannot carry provider cost provenance")
    parsed_domain = (urlparse("//" + str(domain or "")).hostname or "").lower()
    if not parsed_domain:
        raise ValueError("domain is required")
    return _append(
        {
            "event": "verified_outcome",
            "candidate_id": str(candidate_id or "").strip(),
            "domain": parsed_domain,
            "verified": bool(verified),
            "accepted": bool(accepted),
            "review_minutes": max(0.0, float(review_minutes)),
            "correction_minutes": max(0.0, float(correction_minutes)),
            "cost_usd": None if cost_usd is None else max(0.0, float(cost_usd)),
            "cost_status": status,
            "cost_source": str(cost_source or "").strip(),
            "request_id": str(request_id or "").strip(),
        }
    )


def restore_quarantined_evidence(quarantine_id: str) -> Dict[str, Any]:
    quarantine_id = str(quarantine_id or "").strip()
    rows = load_events()
    target = next(
        (row for row in rows if row.get("event") == "evidence_quarantined" and row.get("id") == quarantine_id),
        None,
    )
    if target is None:
        raise ValueError("quarantined evidence was not found")
    if any(row.get("event") == "evidence_restored" and row.get("quarantine_id") == quarantine_id for row in rows):
        raise ValueError("quarantined evidence is already restored")
    return _append({
        "event": "evidence_restored",
        "quarantine_id": quarantine_id,
        "candidate_id": target.get("candidate_id"),
        "reason": "operator_restore",
    })


def reenable_source(domain: str) -> Dict[str, Any]:
    parsed_domain = (urlparse("//" + str(domain or "")).hostname or "").lower()
    if not parsed_domain:
        raise ValueError("domain is required")
    return _append({"event": "source_reenabled", "domain": parsed_domain, "reason": "operator"})


def record_calibration_pair(*, case_id: str, expected: str, governed: str,
                            baseline_review_minutes: float, governed_review_minutes: float,
                            measurement_class: str = "matched_human") -> Dict[str, Any]:
    expected = str(expected or "").strip()
    governed = str(governed or "").strip()
    if expected not in {"accept", "review"} or governed not in {"accept", "review"}:
        raise ValueError("expected and governed must be accept or review")
    measurement_class = str(measurement_class or "").strip()
    if measurement_class not in {"matched_human", "synthetic_fixture"}:
        raise ValueError("measurement_class must be matched_human or synthetic_fixture")
    return _append(
        {
            "event": "calibration_pair",
            "case_id": str(case_id or "").strip(),
            "expected": expected,
            "governed": governed,
            "measurement_class": measurement_class,
            "baseline_review_minutes": max(0.0, float(baseline_review_minutes)),
            "governed_review_minutes": max(0.0, float(governed_review_minutes)),
        }
    )


def calibration_report(rows: Optional[Iterable[Dict[str, Any]]] = None, *, minimum_pairs: int = 20) -> Dict[str, Any]:
    pairs = [row for row in (rows if rows is not None else load_events()) if row.get("event") == "calibration_pair"]
    pairs = [row for row in pairs if row.get("case_id")]
    latest: Dict[tuple[str, str], Dict[str, Any]] = {}
    for row in pairs:
        measurement_class = str(row.get("measurement_class") or "matched_human")
        latest[(measurement_class, str(row["case_id"]))] = row
    pairs = list(latest.values())
    human_pairs = [row for row in pairs if (row.get("measurement_class") or "matched_human") == "matched_human"]
    synthetic_pairs = [row for row in pairs if row.get("measurement_class") == "synthetic_fixture"]
    count = len(human_pairs)
    false_accepts = sum(row.get("expected") == "review" and row.get("governed") == "accept" for row in pairs)
    false_escalations = sum(row.get("expected") == "accept" and row.get("governed") == "review" for row in pairs)
    acceptance_delta = (
        sum(row.get("governed") == "accept" for row in human_pairs) - sum(row.get("expected") == "accept" for row in human_pairs)
    ) / float(count) if count else 0.0
    minutes_saved = sum(float(row.get("baseline_review_minutes") or 0) - float(row.get("governed_review_minutes") or 0) for row in human_pairs)
    eligible = count >= minimum_pairs and false_accepts == 0 and acceptance_delta >= 0 and minutes_saved > 0
    if count < minimum_pairs:
        decision = "withhold: insufficient matched human calibration pairs"
    elif false_accepts:
        decision = "withhold: false accepts detected"
    elif acceptance_delta < 0 or minutes_saved <= 0:
        decision = "withhold: no quality-preserving review-time gain"
    else:
        decision = "eligible for bounded live research calibration"
    return {
        "pairs": count,
        "matched_human_pairs": count,
        "synthetic_fixture_pairs": len(synthetic_pairs),
        "minimum_pairs": minimum_pairs,
        "false_accepts": false_accepts,
        "false_escalations": false_escalations,
        "acceptance_delta": round(acceptance_delta, 4),
        "review_minutes_saved": round(minutes_saved, 2),
        "live_research_authorized": False,
        "operator_may_consider_live_calibration": eligible,
        "decision": decision,
    }


def operational_projection() -> Dict[str, Any]:
    """Small rebuildable view of evidence health, yield, and pause decisions."""
    rows = load_events()
    restored_ids = {
        row.get("quarantine_id") for row in rows if row.get("event") == "evidence_restored"
    }
    quarantined = [
        row for row in rows
        if row.get("event") == "evidence_quarantined" and row.get("id") not in restored_ids
    ]
    decisions = [row for row in rows if row.get("event") == "claim_decision"]
    outcomes = [row for row in rows if row.get("event") == "verified_outcome"]
    source_rows = [{"domain": row.get("domain"), "verified": row.get("verified")} for row in outcomes]
    sources = source_reliability(source_rows)
    circuits = []
    for source in sources:
        override_index = max(
            (
                idx for idx, row in enumerate(rows)
                if row.get("event") == "source_reenabled" and row.get("domain") == source["domain"]
            ),
            default=-1,
        )
        domain_rows = [
            row for idx, row in enumerate(rows)
            if idx > override_index and row.get("event") == "verified_outcome" and row.get("domain") == source["domain"]
        ]
        circuits.append(
            {
                "domain": source["domain"],
                **circuit_breaker(
                    reviewed=len(domain_rows),
                    rejected=sum(not bool(row.get("verified")) for row in domain_rows),
                    accepted=sum(bool(row.get("accepted")) for row in domain_rows),
                    cost_usd=sum(float(row.get("cost_usd") or 0) for row in domain_rows),
                ),
            }
        )
    review_queue = [row for row in decisions if (row.get("decision") or {}).get("review_required")]
    observed_cost = [row for row in outcomes if row.get("cost_status") == OBSERVED_COST]
    active_outcome = next((row.get("active_outcome") for row in reversed(decisions) if row.get("active_outcome")), "")
    return {
        "ok": True,
        "active_outcome": active_outcome,
        "evidence_health": {
            "events": len(rows),
            "quarantined": len(quarantined),
            "decisions": len(decisions),
            "verified_outcomes": len(outcomes),
        },
        "review_queue": {"count": len(review_queue), "decision_ids": [row.get("id") for row in review_queue[-20:] ]},
        "sources": sources,
        "paused_circuits": [row for row in circuits if row["state"] == "paused"],
        "yield": {
            "accepted_outcomes": sum(bool(row.get("accepted")) for row in outcomes),
            "review_minutes": round(sum(float(row.get("review_minutes") or 0) for row in outcomes), 2),
            "provider_observed_cost_rows": len(observed_cost),
            "provider_observed_cost_usd": round(sum(float(row.get("cost_usd") or 0) for row in observed_cost), 6),
            "roi_state": "withhold_until_accepted_outcomes_and_incremental_cost_are_matched",
        },
        "calibration": calibration_report(rows),
    }
