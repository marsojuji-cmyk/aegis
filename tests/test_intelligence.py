"""Intelligence Layer — usage, forecast, memory, compound tick, policy (hardened)."""

import json
import threading

import pytest

from aegis.cache_optimizer import hit_rate, optimize_cache, record_lookup
from aegis.cli import main
from aegis.config import load_config, save_config
from aegis.forecast import predict_budget
from aegis.intelligence import INTEL_LAYER_VERSION, intel_status, tick
from aegis.ledger import record
from aegis.memory import memory_context_block, recall, remember
from aegis.policy_nudges import apply_policy_nudges
from aegis.usage_intel import analyze_usage, waste_signals


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_usage_and_forecast(aegis_tmp):
    record(kind="pack", task="t1", mode="explore", raw_in=1000, processed_in=200)
    record(
        kind="reuse_hit",
        task="t1",
        mode="explore",
        raw_in=1000,
        processed_in=0,
        reuse=True,
    )
    record(
        kind="router_run",
        task="run:mock:x",
        mode="router",
        raw_in=100,
        processed_in=100,
        raw_out=50,
        processed_out=40,
        meta={"provider": "mock", "model": "mock-aegis"},
    )
    # noise should not inflate burn
    record(kind="intel_tick", task="noise", mode="intel", raw_in=0, processed_in=0)
    u = analyze_usage()
    assert u["transactions"] >= 3
    assert u.get("noise_filtered", 0) >= 1
    assert "explore" in (u.get("mode_distribution") or {})
    assert u.get("cache_hit_rate_percent") is not None
    fc = predict_budget(usage=u)
    assert fc["weekly_token_cap"] > 0
    assert "projected_signal" in fc
    assert fc.get("recommended_daily_budget") is not None
    assert 1 <= fc["horizon_days"] <= 30


def test_memory_cross_model(aegis_tmp):
    remember("prefer:mode", "explore first", project="aegis", source_provider="mock")
    remember(
        "prefer:mode",
        "explore first (updated)",
        project="aegis",
        source_provider="grok",
    )
    hits = recall("explore", project="aegis")
    assert hits
    block = memory_context_block("explore pack", project="aegis")
    assert "AEGIS MEMORY" in block
    assert "prefer:mode" in block


def test_memory_concurrent_writes(aegis_tmp):
    errors = []

    def writer(i):
        try:
            remember(f"k{i % 5}", f"v{i}", project="aegis")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    from aegis.memory import memory_stats

    assert memory_stats()["entries"] >= 1


def test_cache_optimizer(aegis_tmp):
    for _ in range(10):
        record_lookup("implement", hit=False)
    for _ in range(2):
        record_lookup("implement", hit=True)
    res = optimize_cache()
    assert res["ok"] is True
    learned = res.get("learned_fallbacks") or {}
    assert "explore" in (learned.get("implement") or [])
    assert hit_rate() >= 0


def test_policy_nudges_idempotent(aegis_tmp):
    cfg = load_config()
    cfg.default_pack_mode = "implement"
    cfg.output_default_max = 2000
    cfg.auto_apply_fixes = True
    save_config(cfg)
    signals = [
        {
            "id": "implement_heavy",
            "fix": "default_mode_explore",
            "title": "impl",
        },
        {
            "id": "low_reduction",
            "fix": "prefer_explore_and_output_profiles",
            "title": "red",
        },
    ]
    cfg2, applied = apply_policy_nudges(signals, load_config(), already_applied=set())
    assert cfg2.default_pack_mode == "explore"
    assert cfg2.output_default_max <= 600
    assert any(a.get("fix") == "default_mode_explore" for a in applied)
    # second pass same week — skipped
    _, applied2 = apply_policy_nudges(
        signals,
        cfg2,
        already_applied={"default_mode_explore", "prefer_explore_and_output_profiles"},
    )
    assert all(a.get("skipped") for a in applied2)
    # reserve never lowered
    assert cfg2.reserve_floor >= 0.8


def test_tick_compound_loop(aegis_tmp):
    record(kind="pack", task="big", mode="explore", raw_in=50_000, processed_in=5_000)
    result = tick(force_report=True)
    assert result["ok"] is True
    assert result.get("actions")
    assert result.get("forecast")
    assert result.get("usage")
    assert result.get("report_path")
    assert result.get("layer_version") == INTEL_LAYER_VERSION
    assert "reserve_healthy" in result
    st = intel_status()
    assert st["state"]["ticks"] >= 1
    assert st.get("layer_version") == INTEL_LAYER_VERSION

    # second tick should not crash; policy idempotent
    r2 = tick(force_report=False)
    assert r2.get("ok") is True


def test_tick_never_raises_on_empty(aegis_tmp):
    r = tick()
    assert "ok" in r
    assert isinstance(r.get("actions"), list)


def test_cli_intel(aegis_tmp):
    assert main(["intel", "status"]) == 0
    assert main(["intel", "forecast"]) == 0
    assert main(["intel", "usage"]) == 0
    assert main(["intel", "membership"]) == 0
    assert main(["intel", "tick", "--force-report"]) == 0


def test_membership_guard_is_honest_without_a_quota_feed(aegis_tmp):
    from aegis.membership_guard import membership_status
    status = membership_status()
    assert status["mode"] == "observe"
    assert status["source"] == "local_estimate_not_chatgpt_quota"


def test_membership_guard_can_set_a_local_reserve(aegis_tmp):
    assert main(["intel", "membership", "--membership-ceiling", "1000", "--membership-reserve", "25"]) == 0
    from aegis.membership_guard import membership_status
    status = membership_status()
    assert status["mode"] == "normal"
    assert status["shadow_weekly_tokens"] == 1000
    assert status["reserve_percent"] == 25.0


def test_waste_signals(aegis_tmp):
    for i in range(12):
        record(
            kind="pack",
            task=f"p{i}",
            mode="implement",
            raw_in=500,
            processed_in=480,
        )
    u = analyze_usage()
    sigs = waste_signals(u)
    assert isinstance(sigs, list)
