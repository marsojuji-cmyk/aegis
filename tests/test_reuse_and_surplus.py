"""Reuse cache + surplus invest gate tests."""

import os
from pathlib import Path

import pytest

from aegis.cli import main
from aegis.fund import invest_credits, load_fund, save_fund, surplus_snapshot
from aegis.ideas import add_idea, invest_in_idea, list_ideas
from aegis.ledger import record
from aegis.pack_cache import get_or_none, pack_key, save_pack


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    home = tmp_path / "aegis-home"
    monkeypatch.setenv("AEGIS_HOME", str(home))
    return home


def test_pack_reuse_hit(aegis_tmp, tmp_path):
    code = tmp_path / "sample.py"
    code.write_text("def foo():\n    return 1\n/* waste */\n")
    path = str(code)
    assert main(["pack", "--task", "demo reuse", "--mode", "explore", path]) == 0
    assert main(["pack", "--task", "demo reuse", "--mode", "explore", path]) == 0
    # second should have written reuse_hit
    from aegis.ledger import read_all

    kinds = [r["kind"] for r in read_all()]
    assert "pack" in kinds
    assert "reuse_hit" in kinds


def test_covering_reuse_on_subset_then_stale_miss(aegis_tmp, tmp_path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("def a():\n    return 1\n")
    b.write_text("def b():\n    return 2\n")
    assert main(["pack", "--task", "both", "--mode", "explore", str(a), str(b)]) == 0
    from aegis.ledger import read_all

    before = len([r for r in read_all() if r["kind"] == "reuse_hit"])
    assert main(["pack", "--task", "only a", "--mode", "explore", str(a)]) == 0
    after = [r for r in read_all() if r["kind"] == "reuse_hit"]
    assert len(after) == before + 1
    a.write_text("def a():\n    return 99\n")
    assert main(["pack", "--task", "changed a", "--mode", "explore", str(a)]) == 0
    kinds = [r["kind"] for r in read_all()]
    assert kinds.count("pack") >= 2


def test_invest_blocked_when_hard_stop(aegis_tmp, monkeypatch):
    # force low remaining capacity via huge processed
    from aegis.config import AegisConfig, save_config

    save_config(AegisConfig(weekly_token_cap=1000, reserve_floor=0.80, throttle_floor=0.50))
    record(kind="pack", task="burn", raw_in=900, processed_in=900)
    snap = surplus_snapshot()
    assert snap["reserve_signal"] in ("throttle", "hard_stop")
    idea = add_idea("should not fund", cost_estimate_tokens=100)
    result = invest_in_idea(idea["id"], credits=50)
    assert result["ok"] is False


def test_invest_when_ok(aegis_tmp):
    from aegis.config import AegisConfig, save_config

    save_config(AegisConfig(weekly_token_cap=1_000_000, reserve_floor=0.80, reinvest_rate=0.5))
    # large savings, small spend
    record(kind="pack", task="save", raw_in=100_000, processed_in=10_000)
    snap = surplus_snapshot()
    assert snap["reserve_signal"] == "ok"
    assert snap["available_credits"] > 0
    idea = add_idea("fund me", cost_estimate_tokens=100)
    # invest small amount
    credits = min(100, snap["available_credits"])
    result = invest_in_idea(idea["id"], credits=credits)
    assert result["ok"] is True
    assert result["idea"]["status"] == "funded"
    assert result["idea"]["funded_credits"] == credits
