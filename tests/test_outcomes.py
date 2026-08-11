from aegis.outcomes import outcome_report, record_outcome


def test_outcome_report_requires_matched_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    assert outcome_report()["routing_authorized"] is False
    record_outcome(task_id="a", variant="baseline", accepted=True, elapsed_seconds=100, retries=2)
    record_outcome(task_id="a", variant="governed", accepted=True, elapsed_seconds=80, retries=1)
    report = outcome_report()
    assert report["paired_tasks"] == 1
    assert report["routing_authorized"] is True
