"""Bounded GrokBot/Hermes orchestration for evidence-first opportunity work.

Hermes keeps private context, policy, and durable outcome records.  GrokBots
work only on externally supplied/public signals and may draft opportunities;
they cannot contact people, spend money, or modify external systems.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse


HERMES_BOTS: Dict[str, Dict[str, Any]] = {
    "conductor": {
        "application": "hermes",
        "purpose": "Route work, retrieve bounded context, and enforce permissions.",
        "may": ["route", "retrieve_context", "create_handoff"],
        "may_not": ["contact", "spend", "publish", "change_permissions"],
    },
    "memory_steward": {
        "application": "hermes",
        "purpose": "Preserve provenance, confidence, retention, and deletion paths.",
        "may": ["deduplicate", "record_outcome", "surface_conflicts"],
        "may_not": ["invent_memory", "silently_overwrite"],
    },
    "evidence_arbiter": {
        "application": "hermes",
        "purpose": "Promote only inspectable evidence into qualified opportunities.",
        "may": ["verify_sources", "qualify", "reject"],
        "may_not": ["treat_inference_as_fact", "approve_outreach"],
    },
    "workflow_closer": {
        "application": "hermes",
        "purpose": "Maintain the active outcome, next action, dependencies, and handoff.",
        "may": ["draft", "organize", "prepare_task"],
        "may_not": ["send", "submit", "create_external_record"],
    },
}

GROK_BOTS: Dict[str, Dict[str, Any]] = {
    "signal_scout": {
        "application": "grok",
        "purpose": "Discover dated, public market and buying signals.",
        "may": ["research_public_sources", "draft_candidate"],
        "may_not": ["claim_unverified_lead", "contact", "scrape_restricted_data"],
    },
    "market_mapper": {
        "application": "grok",
        "purpose": "Map a candidate's stated context to the approved ideal-customer profile.",
        "may": ["compare_public_evidence", "identify_disqualifiers"],
        "may_not": ["infer_private_facts", "override_policy"],
    },
    "value_case_drafter": {
        "application": "grok",
        "purpose": "Draft a falsifiable value hypothesis and research questions.",
        "may": ["draft_value_case", "estimate"],
        "may_not": ["state_estimates_as_observed_roi", "send_outreach"],
    },
    "contrarian": {
        "application": "grok",
        "purpose": "Find missing evidence, alternative explanations, and false-positive risk.",
        "may": ["challenge", "find_disqualifiers"],
        "may_not": ["promote_candidate", "change_decision"],
    },
    "claim_verifier": {
        "application": "grok",
        "purpose": "Collect independent public evidence and explicit counterevidence for a claim.",
        "may": ["research_public_sources", "classify_evidence"],
        "may_not": ["declare_truth", "override_hermes_policy"],
    },
}

EXTERNAL_ACTIONS = {"contact", "spend", "publish", "change_permissions", "submit"}
REQUIRED_EVIDENCE_FIELDS = {"url", "observed_at", "claim"}

# A narrow initial wedge is more testable than a generic "AI consulting" lead
# funnel. It is a proposed pilot strategy until the operator confirms it.
PILOT_STRATEGY: Dict[str, Any] = {
    "offer": "AI Continuity & Workflow Yield Diagnostic",
    "ideal_customer_profile": {
        "organization": "knowledge-intensive team already using multiple AI tools",
        "buyer_problem": "context loss, duplicated work, or unmeasured AI workflow spend",
        "minimum_signal": "publicly stated AI adoption, workflow scale, or operational change",
    },
    "success_metric": "accepted diagnostic conversations per verified review hour",
    "truth_state": "proposed_strategy_pending_operator_confirmation",
}


def bot_catalog() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return a copy-safe catalog grouped by the correct application."""
    return {"hermes": dict(HERMES_BOTS), "grok": dict(GROK_BOTS)}


def pilot_strategy() -> Dict[str, Any]:
    """Return the narrow first offer/ICP used for the matched evaluation pilot."""
    return {
        "offer": PILOT_STRATEGY["offer"],
        "ideal_customer_profile": dict(PILOT_STRATEGY["ideal_customer_profile"]),
        "success_metric": PILOT_STRATEGY["success_metric"],
        "truth_state": PILOT_STRATEGY["truth_state"],
    }


def route_action(action: str) -> Dict[str, Any]:
    """Return the owning application and whether explicit human approval is needed."""
    normalized = str(action or "").strip().lower()
    if normalized in EXTERNAL_ACTIONS:
        return {"application": "hermes", "approval_required": True, "allowed": False}
    if normalized in {"research_public_sources", "draft_candidate", "draft_value_case", "challenge"}:
        return {"application": "grok", "approval_required": False, "allowed": True}
    return {"application": "hermes", "approval_required": False, "allowed": True}


def _parse_observed_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc) if "T" not in raw else datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(raw), datetime.min.time(), tzinfo=timezone.utc)
        except ValueError:
            return None


def qualify_opportunity(
    candidate: Dict[str, Any], *, now: Optional[datetime] = None, max_age_days: int = 90
) -> Dict[str, Any]:
    """Apply deterministic evidence gates; never converts a hypothesis into a fact."""
    now = now or datetime.now(timezone.utc)
    reasons: List[str] = []
    evidence = candidate.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("missing evidence")
        evidence = []

    valid_evidence = 0
    freshness_cutoff = now - timedelta(days=max_age_days)
    for item in evidence:
        if not isinstance(item, dict) or not REQUIRED_EVIDENCE_FIELDS <= set(item):
            reasons.append("incomplete evidence record")
            continue
        observed = _parse_observed_at(item.get("observed_at"))
        if observed is None:
            reasons.append("invalid evidence date")
        elif observed.astimezone(timezone.utc) < freshness_cutoff:
            reasons.append("stale evidence")
        else:
            valid_evidence += 1

    if not str(candidate.get("organization") or "").strip():
        reasons.append("missing organization")
    if not str(candidate.get("fit_hypothesis") or "").strip():
        reasons.append("missing fit hypothesis")
    if not str(candidate.get("next_verification") or "").strip():
        reasons.append("missing next verification")
    if candidate.get("do_not_contact") is not True:
        reasons.append("candidate must retain no-contact default")

    return {
        "stage": "qualified" if not reasons and valid_evidence else "rejected",
        "valid_evidence_count": valid_evidence,
        "reasons": sorted(set(reasons)),
        "outreach_authorized": False,
        "truth_state": "evidence_qualified" if not reasons and valid_evidence else "unverified",
    }


def ingest_public_signals(
    signals: Iterable[Dict[str, Any]], *, strategy: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Convert explicitly supplied public signals into no-contact candidates.

    This is deliberately an adapter, not a scraper: acquisition remains an
    approved provider concern and every input must retain a public HTTPS URL.
    """
    selected = strategy or PILOT_STRATEGY
    offer = str(selected.get("offer") or "")
    candidates: List[Dict[str, Any]] = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        url = str(signal.get("url") or "").strip()
        organization = str(signal.get("organization") or "").strip()
        claim = str(signal.get("claim") or "").strip()
        observed_at = str(signal.get("observed_at") or "").strip()
        if not (url.startswith("https://") and organization and claim and observed_at):
            continue
        candidates.append(
            {
                "organization": organization,
                "fit_hypothesis": (
                    "Public signal may indicate a fit for " + offer + "; "
                    "verify the operational problem before promotion."
                ),
                "next_verification": "Confirm the stated workflow problem and owner from a public source.",
                "do_not_contact": True,
                "evidence": [{"url": url, "observed_at": observed_at, "claim": claim}],
                "source_type": "operator_supplied_public_signal",
                "truth_state": "candidate_hypothesis",
            }
        )
    return candidates


def validate_claim(
    claim: str, evidence: Iterable[Dict[str, Any]], *, impact: str = "low",
    now: Optional[datetime] = None, max_age_days: int = 90
) -> Dict[str, Any]:
    """Let Hermes make a reproducible internal claim decision from Grok evidence.

    Evidence records must include URL, date, claim, and a `stance` of
    `supports` or `contradicts`.  Low-impact internal classification may be
    automated only when two fresh independent domains agree. Conflicts,
    missing proof, and consequential claims remain exceptions for review.
    """
    normalized_claim = str(claim or "").strip()
    impact = str(impact or "low").strip().lower()
    if impact not in {"low", "medium", "high"}:
        raise ValueError("impact must be low, medium, or high")
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    supporting_domains = set()
    contradictory_domains = set()
    invalid = 0
    for item in evidence:
        if not isinstance(item, dict) or not REQUIRED_EVIDENCE_FIELDS <= set(item):
            invalid += 1
            continue
        observed = _parse_observed_at(item.get("observed_at"))
        parsed = urlparse(str(item.get("url") or ""))
        domain = (parsed.hostname or "").lower()
        stance = str(item.get("stance") or "").lower()
        if not domain or observed is None or observed.astimezone(timezone.utc) < cutoff:
            invalid += 1
        elif stance == "supports":
            supporting_domains.add(domain)
        elif stance == "contradicts":
            contradictory_domains.add(domain)
        else:
            invalid += 1

    reasons: List[str] = []
    if not normalized_claim:
        reasons.append("missing claim")
    if invalid:
        reasons.append("invalid_or_stale_evidence")
    if contradictory_domains:
        reasons.append("contradictory_evidence")
    if len(supporting_domains) < 2:
        reasons.append("insufficient_independent_support")
    if impact != "low":
        reasons.append("consequential_claim")
    autonomous = not reasons
    return {
        "claim": normalized_claim,
        "supporting_domains": sorted(supporting_domains),
        "contradictory_domains": sorted(contradictory_domains),
        "impact": impact,
        "decision": "auto_accept_internal" if autonomous else "review_exception",
        "review_required": not autonomous,
        "external_action_authorized": False,
        "reasons": reasons,
        "truth_state": "corroborated_internal" if autonomous else "unresolved",
    }


def quarantine_evidence(
    evidence: Iterable[Dict[str, Any]], *, now: Optional[datetime] = None,
    max_age_days: int = 90
) -> Dict[str, List[Dict[str, Any]]]:
    """Separate usable evidence from malformed, stale, or duplicate records."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    accepted: List[Dict[str, Any]] = []
    quarantined: List[Dict[str, Any]] = []
    seen = set()
    for item in evidence:
        reason = ""
        if not isinstance(item, dict) or not REQUIRED_EVIDENCE_FIELDS <= set(item):
            reason = "incomplete_record"
        else:
            url = str(item.get("url") or "").strip()
            observed = _parse_observed_at(item.get("observed_at"))
            key = (url, str(item.get("claim") or "").strip())
            if not urlparse(url).hostname:
                reason = "invalid_url"
            elif observed is None:
                reason = "invalid_date"
            elif observed.astimezone(timezone.utc) < cutoff:
                reason = "stale_evidence"
            elif key in seen:
                reason = "duplicate_evidence"
            else:
                seen.add(key)
        if reason:
            quarantined.append({"evidence": item, "reason": reason})
        else:
            accepted.append(dict(item))
    return {"accepted": accepted, "quarantined": quarantined}


def source_reliability(outcomes: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calibrate source trust from later verified outcomes with smoothing."""
    grouped: Dict[str, Dict[str, int]] = {}
    for row in outcomes:
        if not isinstance(row, dict):
            continue
        domain = str(row.get("domain") or "").strip().lower()
        verified = row.get("verified")
        if not domain or not isinstance(verified, bool):
            continue
        bucket = grouped.setdefault(domain, {"confirmed": 0, "rejected": 0})
        bucket["confirmed" if verified else "rejected"] += 1
    report = []
    for domain, counts in grouped.items():
        total = counts["confirmed"] + counts["rejected"]
        reliability = (counts["confirmed"] + 1.0) / (total + 2.0)
        report.append(
            {
                "domain": domain,
                "observed_outcomes": total,
                "confirmed": counts["confirmed"],
                "rejected": counts["rejected"],
                "reliability": round(reliability, 3),
                "state": "provisional" if total < 5 else "calibrated",
            }
        )
    return sorted(report, key=lambda item: (item["reliability"], item["observed_outcomes"]), reverse=True)


def circuit_breaker(
    *, reviewed: int, rejected: int, cost_usd: float = 0.0,
    accepted: int = 0, max_rejection_rate: float = 0.35,
    max_cost_per_accepted_usd: float = 5.0, minimum_sample: int = 5
) -> Dict[str, Any]:
    """Pause a source/agent when observed quality or cost becomes unacceptable."""
    reviewed = max(0, int(reviewed))
    rejected = max(0, min(reviewed, int(rejected)))
    accepted = max(0, int(accepted))
    cost_usd = max(0.0, float(cost_usd))
    rejection_rate = (rejected / float(reviewed)) if reviewed else 0.0
    cost_per_accepted = (cost_usd / float(accepted)) if accepted else None
    reasons: List[str] = []
    if reviewed >= minimum_sample and rejection_rate > max_rejection_rate:
        reasons.append("rejection_rate_exceeded")
    if accepted and cost_per_accepted is not None and cost_per_accepted > max_cost_per_accepted_usd:
        reasons.append("cost_per_accepted_exceeded")
    return {
        "state": "paused" if reasons else "active",
        "reasons": reasons,
        "reviewed": reviewed,
        "rejection_rate": round(rejection_rate, 3),
        "cost_per_accepted_usd": None if cost_per_accepted is None else round(cost_per_accepted, 3),
        "requires_operator_review": bool(reasons),
    }


def evaluate_matched_quality(
    baseline: Iterable[Dict[str, Any]], governed: Iterable[Dict[str, Any]],
    *, minimum_pairs: int = 20
) -> Dict[str, Any]:
    """Compare manual and governed qualification on the same candidate IDs.

    Each row records a human review, not a model assertion. `accepted` means
    accepted for a human-approved follow-up decision; it does not authorize
    contact. The gate stays closed until the target sample is reached.
    """
    base_by_id = {
        str(row.get("candidate_id")): row for row in baseline
        if isinstance(row, dict) and row.get("candidate_id")
    }
    governed_by_id = {
        str(row.get("candidate_id")): row for row in governed
        if isinstance(row, dict) and row.get("candidate_id")
    }
    pair_ids = sorted(set(base_by_id) & set(governed_by_id))
    if not pair_ids:
        return {
            "paired_candidates": 0,
            "minimum_pairs": minimum_pairs,
            "decision": "withhold: no matched human-reviewed candidates",
            "outreach_authorized": False,
        }

    base_acceptance = sum(bool(base_by_id[key].get("accepted")) for key in pair_ids)
    governed_acceptance = sum(bool(governed_by_id[key].get("accepted")) for key in pair_ids)
    base_minutes = sum(max(0.0, float(base_by_id[key].get("review_minutes") or 0)) for key in pair_ids)
    governed_minutes = sum(max(0.0, float(governed_by_id[key].get("review_minutes") or 0)) for key in pair_ids)
    acceptance_delta = (governed_acceptance - base_acceptance) / float(len(pair_ids))
    minutes_saved = base_minutes - governed_minutes
    eligible = len(pair_ids) >= minimum_pairs and acceptance_delta >= 0 and minutes_saved > 0
    if len(pair_ids) < minimum_pairs:
        decision = "withhold: insufficient matched human-reviewed candidates"
    elif acceptance_delta < 0:
        decision = "withhold: governed qualification reduced human acceptance"
    elif minutes_saved <= 0:
        decision = "withhold: no demonstrated review-time gain"
    else:
        decision = "eligible for an operator-approved outreach trial"
    return {
        "paired_candidates": len(pair_ids),
        "minimum_pairs": minimum_pairs,
        "acceptance_delta": round(acceptance_delta, 4),
        "review_minutes_saved": round(minutes_saved, 2),
        "decision": decision,
        "outreach_authorized": False,
        "operator_may_consider_trial": eligible,
        "economic_state": "matched_internal_quality_evidence_not_revenue_roi",
    }


def estimate_priority(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Rank review order without presenting a forecast as provider-observed ROI."""
    fit = max(0, min(5, int(candidate.get("fit_score") or 0)))
    urgency = max(0, min(5, int(candidate.get("urgency_score") or 0)))
    confidence = max(0, min(5, int(candidate.get("confidence_score") or 0)))
    review_minutes = max(1, int(candidate.get("review_minutes") or 15))
    score = round(((fit * 0.45) + (urgency * 0.35) + (confidence * 0.20)) / review_minutes, 3)
    return {
        "priority_score": score,
        "economic_state": "estimated_review_priority_not_observed_roi",
        "review_minutes": review_minutes,
    }


def cognition_snapshot(
    *, active_outcome: str, candidate: Dict[str, Any], open_loops: Iterable[str],
    confirmed_strategy: Dict[str, Any], qualification: Dict[str, Any]
) -> Dict[str, Any]:
    """Expose micro, meso, and macro cognition as inspectable state, not persona."""
    return {
        "micro": {
            "active_outcome": active_outcome,
            "candidate_stage": qualification.get("stage"),
            "truth_state": qualification.get("truth_state"),
            "next_action": candidate.get("next_verification"),
            "permission": "no external action without explicit approval",
        },
        "meso": {
            "open_loops": list(open_loops),
            "candidate_organization": candidate.get("organization"),
            "outreach_authorized": False,
        },
        "macro": {
            "confirmed_strategy": dict(confirmed_strategy),
            "update_rule": "explicit confirmation or repeated measured evidence",
            "economic_state": "observed outcomes required before ROI claims",
        },
    }
