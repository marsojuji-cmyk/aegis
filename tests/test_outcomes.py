import json
from pathlib import Path

import pytest

from aegis.cli import main
from aegis.outcomes import (
    finish_pilot,
    init_pilot,
    load_outcome_evidence,
    outcome_report,
    cost_verification_report,
    pilot_status,
    record_outcome,
    start_pilot,
)


def test_outcome_report_requires_matched_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    assert outcome_report()["routing_authorized"] is False
    record_outcome(task_id="a", variant="baseline", accepted=True, elapsed_seconds=100, retries=2, cost_usd=1.0, cost_status="observed", cost_source="hermes")
    record_outcome(task_id="a", variant="governed", accepted=True, elapsed_seconds=80, retries=1, cost_usd=0.5, cost_status="observed", cost_source="hermes")
    report = outcome_report()
    assert report["paired_tasks"] == 1
    assert report["minimum_matched_tasks"] == 10
    assert report["routing_authorized"] is False
    assert "cost provenance pipeline is not verified as trustworthy" in report["decision"]
    assert report["observed_cost_pairs"] == 1
    assert report["cost_comparison_complete"] is True
    assert report["cost_decision"] == "available: all matched pairs have observed provider-cost evidence"
    assert report["total_cost_usd_saved"] == 0.5


def test_outcome_cost_requires_explicit_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    unknown = record_outcome(
        task_id="unknown", variant="baseline", accepted=True, elapsed_seconds=1,
    )
    assert unknown["cost_usd"] is None
    assert unknown["cost_status"] == "unknown"

    legacy = record_outcome(
        task_id="legacy", variant="baseline", accepted=True, elapsed_seconds=1,
        cost_usd=0,
    )
    assert legacy["cost_status"] == "legacy_unknown"

    observed = record_outcome(
        task_id="observed", variant="baseline", accepted=True, elapsed_seconds=1,
        cost_usd=0, cost_status="verified_zero", cost_source="provider_response",
    )
    assert observed["cost_status"] == "verified_zero"


def test_record_outcome_rejects_duplicate_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    record_outcome(
        task_id="DG01", variant="baseline", accepted=True,
        elapsed_seconds=10, workflow="decision_grade_code_change",
    )

    with pytest.raises(ValueError, match="outcome already recorded"):
        record_outcome(
            task_id="DG01", variant="baseline", accepted=False,
            elapsed_seconds=20, workflow="decision_grade_code_change",
        )

    governed = record_outcome(
        task_id="DG01", variant="governed", accepted=True,
        elapsed_seconds=9, workflow="decision_grade_code_change",
    )
    assert governed["variant"] == "governed"


def test_load_outcomes_surfaces_malformed_and_ignored_rows(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AEGIS_HOME", str(home))
    record_outcome(
        task_id="valid", variant="baseline", accepted=True, elapsed_seconds=1,
    )
    path = home / "outcomes.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")
        handle.write(json.dumps({"kind": "not_an_outcome"}) + "\n")

    evidence = load_outcome_evidence()
    assert len(evidence["rows"]) == 1
    assert evidence["malformed_rows"] == 1
    assert evidence["ignored_rows"] == 1
    report = outcome_report()
    assert report["malformed_outcome_rows"] == 1
    assert report["ignored_outcome_rows"] == 1


def test_outcome_report_aggregates_cost_only_for_observed_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    for variant, cost in (("baseline", 1.5), ("governed", 1.0)):
        record_outcome(
            task_id="cost", variant=variant, accepted=True, elapsed_seconds=1,
            cost_usd=cost, cost_status="observed", cost_source="provider_response",
        )
    report = outcome_report()
    assert report["observed_cost_pairs"] == 1
    assert report["cost_comparison_complete"] is True
    assert report["cost_decision"] == "available: all matched pairs have observed provider-cost evidence"
    assert report["total_cost_usd_saved"] == 0.5


def test_outcome_report_excludes_local_cost_sources_from_routing(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    for variant in ("baseline", "governed"):
        record_outcome(
            task_id="local", variant=variant, accepted=True, elapsed_seconds=1,
            cost_usd=0, cost_status="verified_zero", cost_source="local_rehearsal",
        )
    report = outcome_report()
    assert report["observed_cost_pairs"] == 0
    assert report["cost_comparison_complete"] is False
    assert report["routing_authorized"] is False
    audit = cost_verification_report(limit=2)
    assert audit["trustworthy_for_routing"] is False
    assert all("not routing-grade" in gap["error"] for gap in audit["gaps"])


def test_outcome_report_filters_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    for variant in ("baseline", "governed"):
        record_outcome(
            task_id="production", variant=variant, accepted=True, elapsed_seconds=1,
        )
        record_outcome(
            task_id="rehearsal", variant=variant, accepted=True, elapsed_seconds=1,
            workflow="local_rehearsal",
        )
    production = outcome_report()
    rehearsal = outcome_report(workflow="local_rehearsal")
    assert production["workflow"] == "production_code_change"
    assert production["paired_tasks"] == 1
    assert rehearsal["workflow"] == "local_rehearsal"
    assert rehearsal["paired_tasks"] == 1


def test_outcome_report_requires_ten_matched_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    for index in range(10):
        task_id = f"task-{index}"
        record_outcome(task_id=task_id, variant="baseline", accepted=True, elapsed_seconds=100, cost_usd=1.0, cost_status="observed", cost_source="hermes")
        record_outcome(task_id=task_id, variant="governed", accepted=True, elapsed_seconds=80, cost_usd=0.5, cost_status="observed", cost_source="hermes")
    assert outcome_report()["routing_authorized"] is True


def test_outcome_report_requires_cost_reduction(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    for index in range(10):
        task_id = f"task-{index}"
        record_outcome(task_id=task_id, variant="baseline", accepted=True, elapsed_seconds=100, cost_usd=1.0, cost_status="observed", cost_source="hermes")
        record_outcome(task_id=task_id, variant="governed", accepted=True, elapsed_seconds=80, cost_usd=1.5, cost_status="observed", cost_source="hermes")
    report = outcome_report()
    assert report["routing_authorized"] is False
    assert "no quality-preserving cost reduction" in report["decision"]


def test_pilot_runner_copies_orders_times_and_records(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    source = tmp_path / "source"
    source.mkdir()
    (source / "target.py").write_text("value = 1\n", encoding="utf-8")
    (source / ".git").mkdir()

    state = init_pilot(
        task_id="M05", source_dir=str(source), first_variant="governed",
        workspace_root=str(tmp_path / "runs"),
    )
    assert state["order"] == ["governed", "baseline"]
    for workspace in state["workspaces"].values():
        assert (Path(workspace) / "target.py").is_file()
        assert not (Path(workspace) / ".git").exists()

    with pytest.raises(ValueError, match="requires governed"):
        start_pilot("M05", "baseline")
    clock = iter((100.0, 125.5, 200.0, 240.0))
    monkeypatch.setattr("aegis.outcomes.time.time", lambda: next(clock))
    started = start_pilot("M05", "governed")
    assert started["workspace"] == state["workspaces"]["governed"]
    first = finish_pilot("M05", accepted=True, notes="governed accepted")
    assert first["outcome"]["elapsed_seconds"] == 25.5
    assert first["outcome"]["cost_status"] == "unknown"
    assert first["outcome"]["workflow"] == "decision_grade_code_change"
    assert first["pair_complete"] is False

    start_pilot("M05", "baseline")
    second = finish_pilot(
        "M05", accepted=True, notes="baseline accepted",
        cost_usd=0.015, cost_status="observed", cost_source="hermes"
    )
    assert second["outcome"]["elapsed_seconds"] == 40.0
    assert second["outcome"]["cost_usd"] == 0.015
    assert second["outcome"]["cost_status"] == "observed"
    assert second["outcome"]["cost_source"] == "hermes"
    assert second["pair_complete"] is True
    assert set(pilot_status("M05")["results"]) == {"baseline", "governed"}
    assert main(["pilot", "status", "--task-id", "M05"]) == 0
    assert json.loads(capsys.readouterr().out)["order"] == ["governed", "baseline"]


def test_cost_verification_report(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    
    # 1) valid observed
    record_outcome(
        task_id="t1", variant="baseline", accepted=True, elapsed_seconds=10,
        cost_usd=1.0, cost_status="observed", cost_source="hermes",
    )
    # 2) invalid cost_usd
    record_outcome(
        task_id="t2", variant="baseline", accepted=True, elapsed_seconds=10,
        cost_status="unknown",
    )
    # 3) verified_zero with non-zero
    record_outcome(
        task_id="t3", variant="baseline", accepted=True, elapsed_seconds=10,
        cost_usd=0.0, cost_status="verified_zero", cost_source="hermes",
    )

    report = cost_verification_report(limit=3)
    assert report["audited_runs"] == 3
    assert report["trustworthy_for_routing"] is False
    assert len(report["gaps"]) == 1
    assert report["gaps"][0]["task_id"] == "t2"
    assert "cost provenance missing" in report["gaps"][0]["error"]

    report_limit = cost_verification_report(limit=1)
    assert report_limit["audited_runs"] == 1
    assert report_limit["trustworthy_for_routing"] is True
    assert len(report_limit["gaps"]) == 0
