"""Classify outcome-row cost provenance. Does not authorize routing.

Unknown and excluded sources stay untrusted. A complete local rehearsal
or cache row is not incomplete: it is intentionally excluded.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence

from aegis.outcomes import (
    ALL_COST_STATUSES,
    OBSERVED_COST_STATUSES,
    UNTRUSTED_ROUTING_COST_SOURCES,
    cost_verification_report,
    outcome_report,
)

CLASSIFICATIONS = frozenset(
    {
        "intentionally_excluded",
        "routing_relevant_complete",
        "routing_relevant_incomplete",
        "stale_or_misclassified",
        "unknown",
    }
)
IDENTITY_KEYS = ("request_id", "run_id")
EXCLUSION_REASONS = {
    "local_rehearsal": "local_rehearsal is not routing-grade provider evidence",
    "local_cache": "local_cache is not routing-grade provider evidence",
    "mock": "mock is not routing-grade provider evidence",
    "estimated": "estimated is not routing-grade provider evidence",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source(row: Mapping[str, Any]) -> str:
    return _text(row.get("cost_source")).lower()


def identity_present(row: Mapping[str, Any]) -> bool:
    return any(_text(row.get(key)) for key in IDENTITY_KEYS)


def classify_record(row: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return a provenance class. routing_authorized is always false."""
    if not isinstance(row, Mapping):
        return {
            "classification": "unknown",
            "reason": "row is not an object",
            "task_id": "missing",
            "variant": "",
            "cost_source": "",
            "cost_status": "",
            "cost_usd": None,
            "identity_present": False,
            "trusted_for_routing_record": False,
            "routing_authorized": False,
        }
    task_id = _text(row.get("task_id")) or "missing"
    status = _text(row.get("cost_status"))
    source = _source(row)
    usd = row.get("cost_usd")
    identity = identity_present(row)
    base = {
        "task_id": task_id,
        "variant": _text(row.get("variant")),
        "cost_source": source,
        "cost_status": status,
        "cost_usd": usd,
        "identity_present": identity,
        "trusted_for_routing_record": False,
        "routing_authorized": False,
    }
    if source in UNTRUSTED_ROUTING_COST_SOURCES:
        return {
            **base,
            "classification": "intentionally_excluded",
            "reason": EXCLUSION_REASONS[source],
        }
    if not status:
        return {**base, "classification": "unknown", "reason": "missing cost_status"}
    if status not in ALL_COST_STATUSES:
        return {
            **base,
            "classification": "unknown",
            "reason": f"invalid cost_status: {status}",
        }
    if status not in OBSERVED_COST_STATUSES:
        if usd is not None or source:
            return {
                **base,
                "classification": "stale_or_misclassified",
                "reason": f"unknown status must not carry cost fields (status={status})",
            }
        return {
            **base,
            "classification": "routing_relevant_incomplete",
            "reason": f"cost provenance missing (status={status})",
        }
    errors: List[str] = []
    if usd is None or not isinstance(usd, (int, float)):
        errors.append("missing float cost_usd")
    elif status == "verified_zero" and float(usd) != 0.0:
        errors.append("verified_zero requires cost_usd=0.0")
    if not source:
        errors.append("missing cost_source")
    if errors:
        return {
            **base,
            "classification": "routing_relevant_incomplete",
            "reason": "; ".join(errors),
        }
    return {
        **base,
        "classification": "routing_relevant_complete",
        "reason": "observed provider-grade cost with complete fields",
        "trusted_for_routing_record": True,
    }


def classify_gaps(rows: Sequence[Mapping[str, Any]], gaps: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Classify every reported gap. Skip routing-complete rows when pairing. None dropped."""
    remaining = list(gaps)
    reports: List[Dict[str, Any]] = []
    for row in rows:
        classified = classify_record(row)
        if classified.get("trusted_for_routing_record"):
            continue
        task_id = classified["task_id"]
        idx = next(
            (i for i, gap in enumerate(remaining) if (_text(gap.get("task_id")) or "missing") == task_id),
            None,
        )
        if idx is None:
            classified["gap_error"] = ""
            classified["gap_task_id"] = task_id
            reports.append(classified)
            continue
        gap = remaining.pop(idx)
        classified["gap_error"] = _text(gap.get("error"))
        classified["gap_task_id"] = task_id
        reports.append(classified)
    for gap in remaining:
        classified = classify_record(None)
        classified["gap_error"] = _text(gap.get("error"))
        classified["gap_task_id"] = _text(gap.get("task_id")) or "missing"
        reports.append(classified)
    return reports


def classify_window(limit: int = 5) -> Dict[str, Any]:
    """Live-window classification. Never sets routing_authorized true."""
    audit = cost_verification_report(limit=limit)
    from aegis.outcomes import load_outcomes

    all_rows = list(load_outcomes())
    recent = all_rows[-limit:] if limit > 0 else all_rows
    gap_reports = classify_gaps(recent, audit.get("gaps") or [])
    report = outcome_report()
    authorized = bool(report.get("routing_authorized"))
    return {
        "audited_runs": audit["audited_runs"],
        "gaps_found": audit["gaps_found"],
        "trustworthy_for_routing": audit["trustworthy_for_routing"],
        "routing_authorized": False,
        "outcome_routing_authorized": authorized,
        "decision": report.get("decision"),
        "classifications": gap_reports,
        "unclassified_gap_count": max(0, int(audit["gaps_found"]) - len(gap_reports)),
        "unknown_count": sum(1 for item in gap_reports if item["classification"] == "unknown"),
        "excluded_count": sum(
            1 for item in gap_reports if item["classification"] == "intentionally_excluded"
        ),
    }


def window_blocks_routing(window: Mapping[str, Any]) -> bool:
    return window.get("routing_authorized") is not True and window.get("outcome_routing_authorized") is not True
