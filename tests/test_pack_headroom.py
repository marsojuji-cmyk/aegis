"""Pack write refused at zero headroom; reuse still allowed."""

import pytest

from aegis.burn import burn_status
from aegis.cli import main
from aegis.config import AegisConfig, save_config
from aegis.fund import compute_spend_headroom, pack_write_allowed
from aegis.ledger import read_all, record
from aegis.preflight import run_preflight


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _force_zero_headroom(aegis_tmp):
    save_config(AegisConfig(weekly_token_cap=1000, reserve_floor=0.80, throttle_floor=0.50))
    record(kind="pack", task="burn", raw_in=900, processed_in=900)
    assert compute_spend_headroom() == 0


def test_compute_spend_headroom(aegis_tmp):
    save_config(AegisConfig(weekly_token_cap=1_000_000, reserve_floor=0.80))
    assert compute_spend_headroom() == 200_000
    record(kind="pack", task="spend", raw_in=50_000, processed_in=50_000)
    assert compute_spend_headroom() == 150_000


def test_pack_write_refused_at_zero_headroom(aegis_tmp, tmp_path):
    _force_zero_headroom(aegis_tmp)
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n")
    # Trigger legacy seed once so later pack call does not add unrelated ledger rows.
    main(["budget"])
    before = len([r for r in read_all() if r["kind"] == "pack"])
    assert main(["pack", "--task", "blocked", "--mode", "explore", str(f)]) == 4
    assert len([r for r in read_all() if r["kind"] == "pack"]) == before


def test_reuse_allowed_at_zero_headroom(aegis_tmp, tmp_path):
    _force_zero_headroom(aegis_tmp)
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n")
    # seed cache while still healthy
    save_config(AegisConfig(weekly_token_cap=1_000_000, reserve_floor=0.80))
    assert main(["pack", "--task", "seed", "--mode", "explore", str(f)]) == 0
    _force_zero_headroom(aegis_tmp)
    before = len(read_all())
    assert main(["pack", "--task", "seed", "--mode", "explore", str(f)]) == 0
    after = read_all()
    assert len(after) == before + 1
    assert after[-1]["kind"] == "reuse_hit"
    assert after[-1]["processed_in"] == 0


def test_preflight_refuses_pack_at_zero_headroom(aegis_tmp, tmp_path):
    _force_zero_headroom(aegis_tmp)
    f = tmp_path / "m.py"
    f.write_text("def bar():\n    return 2\n")
    before = len(read_all())
    result = run_preflight(paths=[str(f)], task="blocked pf", mode="explore")
    assert result.ok is False
    assert result.exit_code == 4
    assert any("headroom=0" in e for e in result.errors)
    assert len(read_all()) == before


def test_burn_not_healthy_when_safe_daily_zero(aegis_tmp):
    forecast = {
        "week": "test",
        "avg_daily_burn": 5000,
        "recommended_daily_budget": 0,
        "peak_daily_burn": 5000,
        "current_signal": "hard_stop",
        "remaining_pct": 30,
    }
    st = burn_status(
        AegisConfig(),
        usage={"week": "test", "kind_distribution": {}, "mode_distribution": {}},
        forecast=forecast,
        record_events=False,
    )
    assert st["level"] == "critical"
    assert st["ok"] is False
    assert "healthy" not in st["message"].lower()
    assert "headroom" in st["message"].lower() or "reuse" in st["message"].lower()


def test_pack_write_allowed_api(aegis_tmp):
    save_config(AegisConfig(weekly_token_cap=1000, reserve_floor=0.80))
    ok, _ = pack_write_allowed(reuse=False)
    assert ok is True
    record(kind="pack", task="burn", raw_in=900, processed_in=900)
    ok, reason = pack_write_allowed(reuse=False)
    assert ok is False
    assert "headroom=0" in reason
    ok, _ = pack_write_allowed(reuse=True)
    assert ok is True
