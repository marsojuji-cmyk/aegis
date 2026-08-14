"""Durable piggy bank tests."""

import json
import os
from pathlib import Path

import pytest

from aegis.ledger import generate_report, read_all, record


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "aegis-home"))
    return tmp_path / "aegis-home"


def test_record_persists(aegis_tmp):
    e1 = record(kind="pack", task="t1", mode="explore", raw_in=1000, processed_in=200)
    e2 = record(kind="scrub", task="t2", mode="scrub", raw_in=100, processed_in=40)
    assert e1["tokens_saved"] == 800
    rows = read_all()
    assert len(rows) == 2
    assert (aegis_tmp / "ledger.jsonl").is_file()


def test_report_survives_reload(aegis_tmp):
    record(kind="pack", task="a", raw_in=500, processed_in=100)
    r1 = generate_report()
    # simulate new process: just re-read
    r2 = generate_report()
    assert r1["total_tokens_saved"] == r2["total_tokens_saved"] == 400
    assert r2["total_transactions"] == 1
    assert r2["reserve_signal"] in ("ok", "throttle", "hard_stop")


def test_production_report_excludes_local_counterfactuals(aegis_tmp):
    record(kind="pack", raw_in=500, processed_in=100)
    record(kind="router_run", raw_in=20, processed_in=20, raw_out=10, processed_out=10,
           source="provider_observed", request_id="resp_1")
    report = generate_report(accounting="provider_observed")
    assert report["total_tokens_consumed"] == 30
    assert report["observed_transactions"] == 1
    assert report["net_financial_savings_dollars"] == 0
    assert report["local_counterfactual_financial_savings_dollars"] > 0


def test_record_rejects_duplicate_provider_request_id(aegis_tmp):
    first = record(
        kind="router_run", source="provider_observed", request_id=" resp_duplicate ",
        raw_in=10, processed_in=10,
    )
    assert first["request_id"] == "resp_duplicate"

    with pytest.raises(ValueError, match="request_id already recorded"):
        record(
            kind="router_run", source="provider_observed", request_id="resp_duplicate",
            raw_in=10, processed_in=10,
        )

    assert len(read_all()) == 1
    record(kind="router_run", source="provider_observed", request_id="resp_distinct")
    assert len(read_all()) == 2
