"""Pack reuse hit-rate appears in budget report."""

import pytest

from aegis.ledger import generate_report, record


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_reuse_hit_rate_math(aegis_tmp):
    record(kind="pack", task="a", raw_in=1000, processed_in=200, reuse=False)
    record(kind="pack", task="b", raw_in=800, processed_in=100, reuse=False)
    record(kind="reuse_hit", task="a", raw_in=1000, processed_in=0, reuse=True)
    report = generate_report()
    assert report["pack_misses"] == 2
    assert report["reuse_hits"] == 1
    assert report["pack_attempts"] == 3
    assert report["reuse_hit_rate_percent"] == 33.3
    assert report["reuse_tokens_saved"] == 1000
