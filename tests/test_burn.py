"""Burn status levels, config SSOT, events, budget-aware workers."""

import pytest

from aegis.burn import (
    budget_aware_workers,
    burn_ratio,
    burn_status,
    level_for_ratio,
    message_for_level,
    record_level_transition,
)
from aegis.config import AegisConfig, load_config, save_config
from aegis.cli import main


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_level_bands_from_config(aegis_tmp):
    cfg = AegisConfig(
        burn_caution_multiplier=0.80,
        burn_warn_multiplier=1.00,
        burn_warning_multiplier=1.25,
    )
    assert level_for_ratio(0.5, cfg) == "ok"
    assert level_for_ratio(0.85, cfg) == "caution"
    assert level_for_ratio(1.0, cfg) == "warn"
    assert level_for_ratio(1.1, cfg) == "warn"
    assert level_for_ratio(1.25, cfg) == "critical"
    assert level_for_ratio(2.0, cfg) == "critical"


def test_config_ssot_threshold_change(aegis_tmp):
    cfg = load_config()
    cfg.burn_warning_multiplier = 1.50
    cfg.burn_caution_multiplier = 0.90
    save_config(cfg)
    cfg2 = load_config()
    assert cfg2.burn_warning_multiplier == 1.50
    assert level_for_ratio(1.40, cfg2) == "warn"  # under 1.50
    assert level_for_ratio(1.50, cfg2) == "critical"


def test_critical_message_mentions_fan_out(aegis_tmp):
    cfg = AegisConfig()
    msg = message_for_level(
        "critical",
        avg_daily_burn=1400,
        safe_daily=1000,
        ratio=1.4,
        cfg=cfg,
    )
    assert "fan-out" in msg.lower()
    assert "parallel" in msg.lower() or "batch" in msg.lower()


def test_level_transition_events(aegis_tmp):
    ev = record_level_transition(
        "ok",
        "critical",
        ratio=1.4,
        avg_daily_burn=1400,
        safe_daily=1000,
        week="2026-W32",
    )
    assert ev is not None
    assert ev["crossed_125"] is True
    ev2 = record_level_transition(
        "critical",
        "ok",
        ratio=0.5,
        avg_daily_burn=400,
        safe_daily=1000,
        week="2026-W32",
    )
    assert ev2 is not None
    assert ev2["recovered_under_safe"] is True
    assert ev2["direction"] == "down"


def test_budget_aware_workers(aegis_tmp):
    cfg = AegisConfig(budget_aware_mode=True)
    assert budget_aware_workers(16, cfg=cfg, level="ok") == 16
    assert budget_aware_workers(16, cfg=cfg, level="caution") == 12
    assert budget_aware_workers(16, cfg=cfg, level="warn") == 8
    assert budget_aware_workers(16, cfg=cfg, level="critical") == 4
    cfg.budget_aware_mode = False
    assert budget_aware_workers(16, cfg=cfg, level="critical") == 16


def test_burn_status_payload(aegis_tmp):
    # inject forecast so we don't depend on empty ledger math only
    forecast = {
        "week": "test",
        "avg_daily_burn": 1400,
        "recommended_daily_budget": 1000,
        "peak_daily_burn": 1400,
        "current_signal": "ok",
        "remaining_pct": 90,
    }
    st = burn_status(
        AegisConfig(),
        usage={"week": "test", "kind_distribution": {"pack": 5}, "mode_distribution": {"explore": 5}},
        forecast=forecast,
        record_events=True,
    )
    assert st["level"] == "critical"
    assert st["burn_warning"]["active"] is True
    assert "fan-out" in st["message"]
    assert burn_ratio(1400, 1000) == 1.4


def test_cli_burn(aegis_tmp):
    assert main(["intel", "burn"]) == 0
    assert main(["intel", "burn", "--json"]) == 0
