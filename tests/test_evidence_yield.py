import json

import pytest

from aegis import evidence_yield


@pytest.fixture()
def evidence_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _evidence():
    return [
        {"url": "https://one.example/a", "observed_at": "2026-08-20", "claim": "x", "stance": "supports"},
        {"url": "https://two.example/b", "observed_at": "2026-08-21", "claim": "x", "stance": "supports"},
    ]


def test_govern_claim_persists_evidence_and_autonomous_internal_decision(evidence_home):
    result = evidence_yield.govern_claim(
        candidate_id="case-1", claim="AI adoption", evidence=_evidence(), active_outcome="calibrate"
    )
    assert result["decision"]["decision"] == "auto_accept_internal"
    assert result["outreach_authorized"] is False
    rows = evidence_yield.load_events()
    assert [row["event"] for row in rows] == ["evidence_admitted", "evidence_admitted", "claim_decision"]


def test_outcome_requires_provider_provenance_when_claimed(evidence_home):
    with pytest.raises(ValueError, match="provider_observed"):
        evidence_yield.record_verified_outcome(
            candidate_id="case-1", domain="one.example", verified=True, accepted=True,
            review_minutes=1, cost_status="provider_observed"
        )
    row = evidence_yield.record_verified_outcome(
        candidate_id="case-1", domain="one.example", verified=True, accepted=True,
        review_minutes=1, cost_usd=0.02, cost_status="provider_observed",
        cost_source="xai", request_id="req-1"
    )
    assert row["request_id"] == "req-1"


def test_calibration_gate_and_projection(evidence_home):
    for idx in range(20):
        evidence_yield.record_calibration_pair(
            case_id=str(idx), expected="accept", governed="accept",
            baseline_review_minutes=3, governed_review_minutes=1,
        )
    projection = evidence_yield.operational_projection()
    assert projection["calibration"]["operator_may_consider_live_calibration"] is True
    assert projection["calibration"]["live_research_authorized"] is False
    assert projection["yield"]["roi_state"].startswith("withhold")
    assert json.loads(evidence_yield.evidence_yield_path().read_text().splitlines()[0])["event"] == "calibration_pair"
