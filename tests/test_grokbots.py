from datetime import datetime, timezone

from aegis.grokbots import (
    bot_catalog,
    cognition_snapshot,
    estimate_priority,
    evaluate_matched_quality,
    ingest_public_signals,
    pilot_strategy,
    quarantine_evidence,
    qualify_opportunity,
    route_action,
    source_reliability,
    validate_claim,
    circuit_breaker,
)


def _candidate():
    return {
        "organization": "Example Co",
        "fit_hypothesis": "Its public hiring signal matches the approved workflow.",
        "next_verification": "Confirm the stated operational owner.",
        "do_not_contact": True,
        "evidence": [{
            "url": "https://example.test/news",
            "observed_at": "2026-08-20T12:00:00+00:00",
            "claim": "Publicly announced expansion.",
        }],
    }


def test_catalog_assigns_hermes_and_grok_to_distinct_jobs():
    catalog = bot_catalog()
    assert "conductor" in catalog["hermes"]
    assert "signal_scout" in catalog["grok"]
    assert catalog["hermes"]["conductor"]["application"] == "hermes"
    assert catalog["grok"]["signal_scout"]["application"] == "grok"


def test_external_actions_are_approval_gated():
    assert route_action("research_public_sources")["application"] == "grok"
    contact = route_action("contact")
    assert contact["application"] == "hermes"
    assert contact["approval_required"] is True
    assert contact["allowed"] is False


def test_qualification_requires_fresh_complete_evidence_and_no_contact_default():
    result = qualify_opportunity(
        _candidate(), now=datetime(2026, 8, 23, tzinfo=timezone.utc)
    )
    assert result["stage"] == "qualified"
    assert result["outreach_authorized"] is False

    broken = _candidate()
    broken["do_not_contact"] = False
    broken["evidence"] = []
    rejected = qualify_opportunity(broken, now=datetime(2026, 8, 23, tzinfo=timezone.utc))
    assert rejected["stage"] == "rejected"
    assert "missing evidence" in rejected["reasons"]


def test_priority_is_explicitly_an_estimate_and_cognition_is_inspectable():
    candidate = _candidate()
    candidate.update({"fit_score": 5, "urgency_score": 4, "confidence_score": 3, "review_minutes": 10})
    priority = estimate_priority(candidate)
    assert priority["priority_score"] > 0
    assert priority["economic_state"] == "estimated_review_priority_not_observed_roi"

    qualification = qualify_opportunity(candidate, now=datetime(2026, 8, 23, tzinfo=timezone.utc))
    snapshot = cognition_snapshot(
        active_outcome="Qualify first opportunity",
        candidate=candidate,
        open_loops=["verify owner"],
        confirmed_strategy={"icp": "approved only"},
        qualification=qualification,
    )
    assert snapshot["micro"]["permission"] == "no external action without explicit approval"
    assert snapshot["meso"]["open_loops"] == ["verify owner"]
    assert snapshot["macro"]["economic_state"] == "observed outcomes required before ROI claims"


def test_pilot_strategy_and_public_signal_adapter_are_narrow_and_no_contact():
    strategy = pilot_strategy()
    assert strategy["offer"] == "AI Continuity & Workflow Yield Diagnostic"
    assert strategy["truth_state"] == "proposed_strategy_pending_operator_confirmation"

    candidates = ingest_public_signals([{
        "organization": "Example Co",
        "url": "https://example.test/news",
        "observed_at": "2026-08-20T12:00:00+00:00",
        "claim": "Publicly announced AI workflow expansion.",
    }, {"organization": "No URL"}])
    assert len(candidates) == 1
    assert candidates[0]["do_not_contact"] is True
    assert candidates[0]["truth_state"] == "candidate_hypothesis"


def test_matched_quality_requires_sample_and_time_gain_before_a_trial():
    base = [{"candidate_id": "a", "accepted": True, "review_minutes": 12}]
    governed = [{"candidate_id": "a", "accepted": True, "review_minutes": 8}]
    insufficient = evaluate_matched_quality(base, governed)
    assert insufficient["operator_may_consider_trial"] is False
    assert insufficient["outreach_authorized"] is False

    base = [{"candidate_id": str(i), "accepted": True, "review_minutes": 12} for i in range(20)]
    governed = [{"candidate_id": str(i), "accepted": True, "review_minutes": 8} for i in range(20)]
    result = evaluate_matched_quality(base, governed)
    assert result["operator_may_consider_trial"] is True
    assert result["review_minutes_saved"] == 80.0
    assert result["economic_state"] == "matched_internal_quality_evidence_not_revenue_roi"


def test_claim_validation_automates_low_impact_corroborated_classification_only():
    evidence = [
        {"url": "https://one.example/a", "observed_at": "2026-08-20", "claim": "x", "stance": "supports"},
        {"url": "https://two.example/b", "observed_at": "2026-08-21", "claim": "x", "stance": "supports"},
    ]
    accepted = validate_claim("Company announced AI adoption", evidence, now=datetime(2026, 8, 23, tzinfo=timezone.utc))
    assert accepted["decision"] == "auto_accept_internal"
    assert accepted["review_required"] is False
    assert accepted["external_action_authorized"] is False

    conflicted = validate_claim(
        "Company announced AI adoption",
        evidence + [{"url": "https://three.example/c", "observed_at": "2026-08-22", "claim": "x", "stance": "contradicts"}],
        now=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )
    assert conflicted["decision"] == "review_exception"
    assert "contradictory_evidence" in conflicted["reasons"]

    high_impact = validate_claim("Company announced AI adoption", evidence, impact="high", now=datetime(2026, 8, 23, tzinfo=timezone.utc))
    assert high_impact["review_required"] is True


def test_data_immune_system_quarantines_bad_records_and_calibrates_sources():
    evidence = [
        {"url": "https://one.example/a", "observed_at": "2026-08-20", "claim": "x"},
        {"url": "https://one.example/a", "observed_at": "2026-08-20", "claim": "x"},
        {"url": "not-a-url", "observed_at": "2026-08-20", "claim": "x"},
    ]
    result = quarantine_evidence(evidence, now=datetime(2026, 8, 23, tzinfo=timezone.utc))
    assert len(result["accepted"]) == 1
    assert {row["reason"] for row in result["quarantined"]} == {"duplicate_evidence", "invalid_url"}

    sources = source_reliability([
        {"domain": "good.example", "verified": True},
        {"domain": "good.example", "verified": True},
        {"domain": "bad.example", "verified": False},
    ])
    assert sources[0]["domain"] == "good.example"
    assert sources[0]["state"] == "provisional"


def test_circuit_breaker_pauses_bad_or_expensive_work():
    paused = circuit_breaker(reviewed=10, rejected=5, accepted=2, cost_usd=20)
    assert paused["state"] == "paused"
    assert paused["requires_operator_review"] is True
    active = circuit_breaker(reviewed=10, rejected=2, accepted=4, cost_usd=8)
    assert active["state"] == "active"
