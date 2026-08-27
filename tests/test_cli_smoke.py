"""CLI smoke — pack/scrub/budget with durable home."""

import os
import tempfile

import pytest

from aegis.cli import main


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_doctor_exit_zero(aegis_tmp):
    assert main(["doctor"]) == 0


def test_scrub_pack_budget_output(aegis_tmp):
    code = '''
/* License waste header */
"""Module docstring waste"""

def hello(x):
    return x + 1
'''
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        assert main(["scrub", path]) == 0
        assert main(["pack", "--task", "smoke", "--mode", "explore", path]) == 0
        assert main(["budget"]) == 0
        assert main(["output", "--profile", "brief", "--max", "200"]) == 0
        assert main(["record-out", "--raw", "900", "--actual", "200"]) == 0
        assert main(["surplus"]) == 0
        assert main(["idea", "list"]) == 0
    finally:
        os.unlink(path)


def test_doctor(aegis_tmp):
    from aegis.doctor import doctor_report

    r = doctor_report()
    assert r["epoch"] == "1.3"
    assert str(r.get("version", "")).startswith("1.3.")


def test_outcome_cli_records_unknown_cost(aegis_tmp):
    from aegis.outcomes import load_outcomes

    assert main([
        "outcome", "record", "--task-id", "unknown-cost", "--variant", "governed",
        "--accepted", "--elapsed-seconds", "1",
    ]) == 0
    row = list(load_outcomes())[-1]
    assert row["cost_usd"] is None
    assert row["cost_status"] == "unknown"
    assert row["cost_source"] == ""
