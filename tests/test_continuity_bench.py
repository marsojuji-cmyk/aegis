"""Continuity A/B bench tests."""

from pathlib import Path

import pytest

from aegis.continuity_bench import run_bench


FIXTURE = Path("/Users/a100/Documents/ChatGPT/Memory utility Labs/experiments/continuity-assurance/cases.json")


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.mark.skipif(not FIXTURE.is_file(), reason="MUL continuity fixture not present")
def test_governed_beats_baseline_on_fixture(aegis_tmp):
    report = run_bench(FIXTURE)
    assert report["baseline"]["cases_total"] == 6
    assert report["governed"]["cases_passed"] >= report["baseline"]["cases_passed"]
    assert report["governed"]["handoff_failures"] < report["baseline"]["handoff_failures"]
    assert report["governed"]["unsupported_recalls"] < report["baseline"]["unsupported_recalls"]
    assert report["delta"]["pass_rate_governed"] == 1.0
