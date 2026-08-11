"""Budget-Aware Mode — hysteresis, shedding, dry-run, tick gating."""

import pytest

from aegis.budget_aware import (
    apply_hysteresis,
    evaluate,
    plan_for_band,
    should_run_module,
    simulate,
)
from aegis.cli import main
from aegis.config import AegisConfig, load_config, save_config
from aegis.intelligence import tick


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_hysteresis_holds_sticky_band(aegis_tmp):
    cfg = AegisConfig(budget_recovery_hysteresis=0.10)
    # sticky warn (entry 1.0); ratio 0.95 should stay warn
    assert apply_hysteresis("caution", "warn", 0.95, cfg) == "warn"
    # ratio 0.85 → below 1.0 - 0.10 = 0.90 → demote
    assert apply_hysteresis("caution", "warn", 0.85, cfg) == "caution"
    # escalate immediately
    assert apply_hysteresis("critical", "ok", 1.5, cfg) == "critical"


def test_plan_emergency_sheds_low_priority(aegis_tmp):
    plan = plan_for_band("emergency")
    assert "usage_intel" in plan["run"] or "usage_intel" in plan["throttle"]
    assert "exploratory_enrichment" in plan["shed"]
    assert should_run_module(plan, "surplus_sync") is True
    assert should_run_module(plan, "exploratory_enrichment") is False


def test_plan_adaptive_throttles(aegis_tmp):
    plan = plan_for_band("adaptive")
    assert plan["band"] == "adaptive"
    # enrichment modules should not be full-run
    assert "exploratory_enrichment" in (plan["shed"] + plan["throttle"])


def test_simulate_dry_run(aegis_tmp):
    sim = simulate("emergency")
    assert sim["dry_run"] is True
    assert sim["band"] == "emergency"
    assert sim["modules_shed"]
    # dry-run should not stick
    live = evaluate(dry_run=True)
    assert live["dry_run"] is True


def test_evaluate_disabled(aegis_tmp):
    cfg = load_config()
    cfg.budget_aware_mode = False
    save_config(cfg)
    burn = {
        "ratio": 2.0,
        "level": "critical",
        "avg_daily_burn": 2000,
        "safe_daily": 1000,
        "message": "x",
    }
    st = evaluate(load_config(), burn=burn, dry_run=False)
    assert st["enabled"] is False
    assert st["band"] == "ok"


def test_tick_respects_shed(aegis_tmp):
    # force emergency via evaluate sticky then tick
    burn = {
        "ratio": 1.5,
        "level": "critical",
        "avg_daily_burn": 1500,
        "safe_daily": 1000,
        "message": "crit",
    }
    evaluate(AegisConfig(), burn=burn, dry_run=False)
    # seed ledger so tick has data
    from aegis.ledger import record

    record(kind="pack", task="t", mode="explore", raw_in=1000, processed_in=100)
    r = tick(force_report=True)
    assert r.get("ok") is True
    ba = r.get("budget_aware") or {}
    # may be emergency if burn ratio high from synthetic ledger
    assert "band" in ba
    actions = " ".join(r.get("actions") or [])
    assert "Budget:" in actions or "budget" in actions.lower()


def test_cli_budget(aegis_tmp):
    assert main(["intel", "budget"]) == 0
    assert main(["intel", "budget", "--dry-run"]) == 0
    assert main(["intel", "budget", "--simulate", "adaptive", "--json"]) == 0
