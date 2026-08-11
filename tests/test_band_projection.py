"""Projection + hysteresis edge cases for expanded band state machine."""

import time

import pytest

from aegis.band_fanout import (
    attach_fanout,
    detach_fanout,
    fanout_clear,
    fanout_log,
    format_menu_line,
)
from aegis.budget_aware import (
    apply_hysteresis,
    evaluate,
    get_event_bus,
    project_usage,
    instantaneous_with_projection,
)
from aegis.config import AegisConfig


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_project_usage_linear():
    # 0.5 → 0.6 over 10s → rate 0.01/s → +60s → 1.2
    p = project_usage(0.6, 0.5, 10.0, 60.0)
    assert abs(p - 1.2) < 1e-9
    assert project_usage(0.5, 0.5, 0.0, 60.0) == 0.5


def test_projection_forces_early_enter(aegis_tmp):
    cfg = AegisConfig(
        budget_use_projection=True,
        burn_caution_multiplier=0.80,
        burn_warn_multiplier=1.00,
        burn_warning_multiplier=1.25,
    )
    # Rising fast: 0.5 → 0.7 in 10s projects well past 1.0 over 60s horizon
    # rate = 0.02/s * 60 = 1.2 → projected 0.7+1.2 = 1.9 → critical
    level, projected = instantaneous_with_projection(
        0.7,
        previous_ratio=0.5,
        previous_ts="2026-08-08T12:00:00+00:00",
        cfg=cfg,
        now_ts="2026-08-08T12:00:10+00:00",
    )
    assert projected is not None and projected > 1.25
    assert level == "critical"


def test_projection_disabled(aegis_tmp):
    cfg = AegisConfig(budget_use_projection=False)
    level, projected = instantaneous_with_projection(
        0.7,
        previous_ratio=0.5,
        previous_ts="2026-08-08T12:00:00+00:00",
        cfg=cfg,
        now_ts="2026-08-08T12:00:10+00:00",
    )
    assert projected is None
    assert level == "ok"  # 0.7 < 0.80 caution


def test_hysteresis_still_holds_with_projection_path(aegis_tmp):
    cfg = AegisConfig(budget_recovery_hysteresis=0.10)
    # sticky critical; low ratio demotes only under exit
    assert apply_hysteresis("ok", "critical", 1.20, cfg) == "critical"
    assert apply_hysteresis("ok", "critical", 1.10, cfg) == "ok"


def test_fanout_bus_receives_transitions(aegis_tmp):
    fanout_clear()
    detach_fanout()
    attach_fanout(console=False)
    bus = get_event_bus()
    # seed two evaluates with rising ratio via burn dict
    b1 = {"ratio": 0.5, "level": "ok", "avg_daily_burn": 500, "safe_daily": 1000, "message": "x"}
    evaluate(AegisConfig(), burn=b1, dry_run=False)
    b2 = {
        "ratio": 1.3,
        "level": "critical",
        "avg_daily_burn": 1300,
        "safe_daily": 1000,
        "message": "y",
    }
    st = evaluate(AegisConfig(), burn=b2, dry_run=False)
    assert st["band"] == "emergency"
    # bus should have at least one transition if sticky moved
    log = fanout_log(10)
    bus_log = bus.recent(10)
    assert log or bus_log  # either adapter or bus recorded
    if log:
        line = format_menu_line(log[0])
        assert "Budget:" in line
    detach_fanout()


def test_evaluate_records_projected_ratio_field(aegis_tmp):
    cfg = AegisConfig(budget_use_projection=True)
    b1 = {"ratio": 0.4, "level": "ok", "avg_daily_burn": 400, "safe_daily": 1000, "message": "a"}
    evaluate(cfg, burn=b1, dry_run=False)
    time.sleep(0.05)
    b2 = {"ratio": 0.55, "level": "ok", "avg_daily_burn": 550, "safe_daily": 1000, "message": "b"}
    st = evaluate(cfg, burn=b2, dry_run=False)
    # projected may be present after second sample
    assert "projected_ratio" in st
