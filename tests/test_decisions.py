"""Decision register health probes."""

import pytest

from aegis.cli import main
from aegis.decisions import DECISION_IDS, health


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_USER", raising=False)
    return tmp_path / "home"


def test_health_covers_every_decision(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    report = health()
    ids = [row["id"] for row in report["decisions"]]
    assert ids == list(DECISION_IDS)
    assert len(ids) == 21
    by_id = {row["id"]: row for row in report["decisions"]}
    assert by_id["D-011"]["verdict"] == "keep"
    assert by_id["D-014"]["verdict"] == "superseded"
    assert by_id["D-015"]["verdict"] == "keep"
    assert by_id["D-019"]["verdict"] == "park"
    assert by_id["D-031"]["aligned"] is True


def test_cli_decisions_health(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    assert main(["decisions", "health", "--json"]) in (0, 1)
