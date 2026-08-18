"""Provenance classification. Does not authorize routing."""

import json

import pytest

from aegis.cost_provenance import (
    classify_gaps,
    classify_record,
    classify_window,
    identity_present,
)
from aegis.outcomes import cost_verification_report, outcome_report, record_outcome


def test_local_rehearsal_is_intentionally_excluded():
    out = classify_record(
        {
            "task_id": "DG09",
            "variant": "governed",
            "cost_status": "verified_zero",
            "cost_usd": 0.0,
            "cost_source": "local_rehearsal",
        }
    )
    assert out["classification"] == "intentionally_excluded"
    assert out["routing_authorized"] is False
    assert out["trusted_for_routing_record"] is False
    assert "local_rehearsal" in out["reason"]


def test_local_cache_is_intentionally_excluded():
    out = classify_record(
        {
            "task_id": "DG11",
            "variant": "governed",
            "cost_status": "verified_zero",
            "cost_usd": 0.0,
            "cost_source": "local_cache",
        }
    )
    assert out["classification"] == "intentionally_excluded"
    assert out["routing_authorized"] is False


def test_missing_cost_value_is_incomplete():
    out = classify_record(
        {"task_id": "x", "cost_status": "observed", "cost_source": "hermes", "cost_usd": None}
    )
    assert out["classification"] == "routing_relevant_incomplete"
    assert out["routing_authorized"] is False


def test_missing_cost_source_is_incomplete():
    out = classify_record(
        {"task_id": "x", "cost_status": "observed", "cost_usd": 1.0, "cost_source": ""}
    )
    assert out["classification"] == "routing_relevant_incomplete"
    assert out["routing_authorized"] is False


def test_missing_status_is_unknown():
    out = classify_record({"task_id": "x", "cost_usd": 1.0, "cost_source": "hermes"})
    assert out["classification"] == "unknown"
    assert out["routing_authorized"] is False


def test_missing_request_run_identity_does_not_trust_excluded_rows():
    row = {
        "task_id": "DG10",
        "cost_status": "observed",
        "cost_usd": 0.05,
        "cost_source": "local_rehearsal",
    }
    assert identity_present(row) is False
    out = classify_record(row)
    assert out["identity_present"] is False
    assert out["classification"] == "intentionally_excluded"
    assert out["routing_authorized"] is False


def test_stale_source_on_unknown_status_is_misclassified():
    out = classify_record(
        {
            "task_id": "stale",
            "cost_status": "unknown",
            "cost_usd": 1.0,
            "cost_source": "openai_api",
        }
    )
    assert out["classification"] == "stale_or_misclassified"
    assert out["routing_authorized"] is False


def test_explicit_exclusion_reason_is_auditable():
    out = classify_record(
        {
            "task_id": "ex",
            "cost_status": "verified_zero",
            "cost_usd": 0.0,
            "cost_source": "mock",
        }
    )
    assert out["classification"] == "intentionally_excluded"
    assert out["reason"] == "mock is not routing-grade provider evidence"


def test_ambiguous_row_is_unknown():
    out = classify_record({})
    assert out["classification"] == "unknown"
    assert out["task_id"] == "missing"
    assert out["routing_authorized"] is False
    assert classify_record(None)["classification"] == "unknown"


def test_provider_complete_record_is_not_a_window_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    row = {
        "task_id": "ok",
        "variant": "baseline",
        "cost_status": "observed",
        "cost_usd": 0.05,
        "cost_source": "openai_api",
        "request_id": "req-1",
        "run_id": "run-1",
    }
    out = classify_record(row)
    assert out["classification"] == "routing_relevant_complete"
    assert out["trusted_for_routing_record"] is True
    assert out["routing_authorized"] is False
    assert outcome_report()["routing_authorized"] is False


def test_four_live_style_gaps_are_classified_and_not_dropped():
    rows = [
        {"task_id": "DG09", "variant": "governed", "cost_status": "verified_zero", "cost_usd": 0.0, "cost_source": "local_rehearsal"},
        {"task_id": "DG10", "variant": "baseline", "cost_status": "observed", "cost_usd": 0.05, "cost_source": "local_rehearsal"},
        {"task_id": "DG10", "variant": "governed", "cost_status": "verified_zero", "cost_usd": 0.0, "cost_source": "local_rehearsal"},
        {"task_id": "DG11", "variant": "governed", "cost_status": "verified_zero", "cost_usd": 0.0, "cost_source": "local_cache"},
    ]
    gaps = [
        {"task_id": "DG09", "error": "cost_source is not routing-grade provider evidence: local_rehearsal"},
        {"task_id": "DG10", "error": "cost_source is not routing-grade provider evidence: local_rehearsal"},
        {"task_id": "DG10", "error": "cost_source is not routing-grade provider evidence: local_rehearsal"},
        {"task_id": "DG11", "error": "cost_source is not routing-grade provider evidence: local_cache"},
    ]
    reports = classify_gaps(rows, gaps)
    assert len(reports) == 4
    assert {item["classification"] for item in reports} == {"intentionally_excluded"}
    assert all(item["routing_authorized"] is False for item in reports)
    assert [item["cost_source"] for item in reports] == [
        "local_rehearsal",
        "local_rehearsal",
        "local_rehearsal",
        "local_cache",
    ]


def test_d033_regression_untrusted_window_withholds(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    record_outcome(
        task_id="DG09", variant="governed", accepted=True, elapsed_seconds=1,
        cost_usd=0.0, cost_status="verified_zero", cost_source="local_rehearsal",
        workflow="decision_grade_code_change",
    )
    record_outcome(
        task_id="DG10", variant="baseline", accepted=True, elapsed_seconds=1,
        cost_usd=0.05, cost_status="observed", cost_source="local_rehearsal",
        workflow="decision_grade_code_change",
    )
    record_outcome(
        task_id="DG10", variant="governed", accepted=True, elapsed_seconds=1,
        cost_usd=0.0, cost_status="verified_zero", cost_source="local_rehearsal",
        workflow="decision_grade_code_change",
    )
    record_outcome(
        task_id="DG11", variant="baseline", accepted=True, elapsed_seconds=1,
        cost_usd=0.05, cost_status="observed", cost_source="openai_api",
        workflow="decision_grade_code_change",
    )
    record_outcome(
        task_id="DG11", variant="governed", accepted=True, elapsed_seconds=1,
        cost_usd=0.0, cost_status="verified_zero", cost_source="local_cache",
        workflow="decision_grade_code_change",
    )
    audit = cost_verification_report(limit=5)
    assert audit["gaps_found"] == 4
    assert audit["trustworthy_for_routing"] is False
    window = classify_window(limit=5)
    assert window["gaps_found"] == 4
    assert window["excluded_count"] == 4
    assert window["unknown_count"] == 0
    assert window["unclassified_gap_count"] == 0
    assert window["routing_authorized"] is False
    assert window["outcome_routing_authorized"] is False
    assert outcome_report()["routing_authorized"] is False


def test_verify_cost_cli_labels_exclusions_and_never_authorizes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    from aegis.cli import main

    record_outcome(
        task_id="DG09", variant="governed", accepted=True, elapsed_seconds=1,
        cost_usd=0.0, cost_status="verified_zero", cost_source="local_rehearsal",
        workflow="decision_grade_code_change",
    )
    record_outcome(
        task_id="ok", variant="baseline", accepted=True, elapsed_seconds=1,
        cost_usd=0.05, cost_status="observed", cost_source="openai_api",
        workflow="decision_grade_code_change",
    )
    assert main(["outcome", "verify-cost", "--limit", "2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["routing_authorized"] is False
    assert payload["trustworthy_for_routing"] is False
    assert payload["excluded_count"] == 1
    assert payload["classifications"][0]["classification"] == "intentionally_excluded"
