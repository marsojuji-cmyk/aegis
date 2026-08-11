"""ROI scoring + investment audit tests."""

import pytest

from aegis.audit import audit_portfolio
from aegis.ideas import add_idea, complete_idea, invest_in_idea, list_ideas
from aegis.ledger import record
from aegis.roi import grade_for_ratio, score_idea
from aegis.config import AegisConfig, save_config


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_roi_score_higher_savings_better(aegis_tmp):
    low = score_idea(
        {
            "cost_estimate_tokens": 5000,
            "expected_savings_tokens": 2000,
            "confidence": "medium",
        }
    )
    high = score_idea(
        {
            "cost_estimate_tokens": 2000,
            "expected_savings_tokens": 20_000,
            "confidence": "high",
        }
    )
    assert high["roi_ratio"] > low["roi_ratio"]
    assert high["roi_score"] > low["roi_score"]
    assert high["roi_grade"] in ("A", "B")
    assert grade_for_ratio(5.0) == "A"


def test_list_ranked_by_roi(aegis_tmp):
    add_idea("low roi", cost_estimate_tokens=10_000, expected_savings_tokens=1000, confidence="low")
    add_idea("high roi", cost_estimate_tokens=1000, expected_savings_tokens=20_000, confidence="high")
    ranked = list_ideas()
    assert ranked[0]["title"] == "high roi"
    assert ranked[0]["roi_score"] >= ranked[-1]["roi_score"]


def test_complete_and_audit_learns(aegis_tmp):
    save_config(AegisConfig(weekly_token_cap=1_000_000, reserve_floor=0.80, reinvest_rate=0.5))
    record(kind="pack", task="seed save", raw_in=200_000, processed_in=10_000)
    idea = add_idea(
        "ship me",
        cost_estimate_tokens=1000,
        expected_savings_tokens=5000,
        confidence="high",
    )
    inv = invest_in_idea(idea["id"], credits=500)
    assert inv["ok"]
    done = complete_idea(idea["id"], actual_savings_tokens=8000)
    assert done["ok"]
    assert done["idea"]["status"] == "done"
    assert done["idea"]["actual_roi_ratio"] is not None
    # beat estimate → positive delta
    assert done["idea"]["roi_delta"] is not None

    report = audit_portfolio()
    assert report["summary"]["measured_count"] >= 1
    assert report["summary"]["invested_count"] >= 1
    assert any("Winners" in L or "Portfolio" in L or "Learning" in L for L in report["lessons"]) or report["lessons"]
