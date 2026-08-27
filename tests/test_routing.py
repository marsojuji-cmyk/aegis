"""Tiny-chat routing trial. Implement packs stay on the requested model."""

import pytest

from aegis.outcomes import record_outcome
from aegis.portable import init_home
from aegis.receipt_collect import PAIR_WORKFLOW
from aegis.routing import BASELINE_MODEL, GOVERNED_MODEL, apply_route, workflow_compare
from aegis.yield_proof import yield_is_honest


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AEGIS_HOME", str(home))
    monkeypatch.delenv("AEGIS_USER", raising=False)
    return home


def _pairs(n: int, *, baseline_usd: float, governed_usd: float, workflow: str = PAIR_WORKFLOW) -> None:
    for index in range(n):
        task_id = f"rt-{index}"
        for variant, usd in (("baseline", baseline_usd), ("governed", governed_usd)):
            record_outcome(
                task_id=task_id,
                variant=variant,
                accepted=True,
                elapsed_seconds=2.0 if variant == "baseline" else 1.0,
                cost_usd=usd,
                cost_status="observed",
                cost_source="nous_api",
                workflow=workflow,
            )


def test_apply_route_off_without_ten_pairs(aegis_tmp):
    init_home()
    _pairs(1, baseline_usd=1.0, governed_usd=0.4)
    out = apply_route(model=BASELINE_MODEL, mode="explore")
    assert out["applied"] is False
    assert out["model"] == BASELINE_MODEL
    assert out["reason"] == "not_eligible"
    assert out["savings_percent"] == 60.0


def test_apply_route_tiny_chat_on_implement_off(aegis_tmp):
    init_home()
    _pairs(10, baseline_usd=0.00005, governed_usd=0.00001)
    explore = apply_route(model=BASELINE_MODEL, mode="explore")
    assert explore["applied"] is True
    assert explore["model"] == GOVERNED_MODEL
    assert explore["reason"] == "tiny_chat_trial"
    assert explore["routing_authorized"] is True
    assert explore["savings_percent"] == 80.0

    implement = apply_route(model=BASELINE_MODEL, mode="implement")
    assert implement["applied"] is False
    assert implement["model"] == BASELINE_MODEL
    assert implement["reason"] == "implement_pack_loses_money"
    assert implement["routing_authorized"] is True

    mock = apply_route(model="mock", mode="explore")
    assert mock["applied"] is False
    assert mock["reason"] == "mock"


def test_workflow_compare_shows_loss_on_pack_scale(aegis_tmp):
    init_home()
    _pairs(5, baseline_usd=0.00005, governed_usd=0.001286, workflow="aegis_pack_scale")
    _pairs(10, baseline_usd=0.00005, governed_usd=0.000029)
    rows = {row["workflow"]: row for row in workflow_compare()}
    assert rows["matched_provider_pairs"]["savings_percent"] == 42.0
    assert rows["matched_provider_pairs"]["routing_authorized"] is True
    assert rows["aegis_pack_scale"]["savings_percent"] < 0
    assert rows["aegis_pack_scale"]["routing_authorized"] is False


def test_yield_is_honest_rejects_fake_percent():
    assert yield_is_honest({"savings_percent": None, "billed_pairs": {}}) is True
    assert yield_is_honest(
        {"savings_percent": 41.3, "billed_pairs": {"savings_percent": 41.3, "observed_cost_pairs": 20}}
    ) is True
    assert yield_is_honest(
        {"savings_percent": 90.0, "billed_pairs": {"savings_percent": 41.3, "observed_cost_pairs": 20}}
    ) is False
