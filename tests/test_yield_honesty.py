"""Honesty yield surfaces live ledger + billed-pair numbers. savings_percent stays null."""

import json

import pytest

from aegis.cli import main
from aegis.demo import format_run, honesty, run
from aegis.doctor import doctor_report
from aegis.ledger import record
from aegis.outcomes import record_outcome
from aegis.portable import init_home
from aegis.receipt_collect import PAIR_WORKFLOW
from aegis.yield_proof import prove, yield_report


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("AEGIS_HOME", str(home))
    monkeypatch.delenv("AEGIS_USER", raising=False)
    return home


def _pair(*, task_id: str, baseline_usd: float, governed_usd: float) -> None:
    for variant, usd in (("baseline", baseline_usd), ("governed", governed_usd)):
        record_outcome(
            task_id=task_id,
            variant=variant,
            accepted=True,
            elapsed_seconds=2.0 if variant == "baseline" else 1.0,
            cost_usd=usd,
            cost_status="observed",
            cost_source="nous_api",
            workflow=PAIR_WORKFLOW,
        )


def test_yield_report_empty_home_is_numeric_not_null(aegis_tmp):
    init_home()
    body = yield_report()
    assert body["ok"] is True
    assert body["savings_percent"] is None
    assert body["admitted_pair"] is False
    assert body["ledger_tokens_saved_local"] == 0
    assert body["ledger_tokens_consumed"] == 0
    assert body["ledger_reduction_percent_local"] == 0.0
    assert body["reuse_hit_rate"] == 0.0
    billed = body["billed_pairs"]
    assert billed["paired_tasks"] == 0
    assert billed["observed_cost_pairs"] == 0
    assert billed["total_cost_usd_saved"] is None
    assert billed["baseline_mean_usd"] is None
    assert billed["routing_authorized"] is False


def test_yield_report_uses_live_ledger_and_billed_pairs(aegis_tmp):
    init_home()
    record(kind="pack", task="yield-honesty", mode="explore", raw_in=1000, processed_in=400)
    _pair(task_id="yh-1", baseline_usd=1.0, governed_usd=0.4)

    body = yield_report()
    assert body["savings_percent"] is None
    assert body["ledger_tokens_saved_local"] == 600
    assert body["ledger_tokens_consumed"] == 400
    assert body["ledger_reduction_percent_local"] == 60.0
    billed = body["billed_pairs"]
    assert billed["paired_tasks"] == 1
    assert billed["observed_cost_pairs"] == 1
    assert billed["cost_comparison_complete"] is True
    assert billed["baseline_mean_usd"] == 1.0
    assert billed["governed_mean_usd"] == 0.4
    assert billed["total_cost_usd_saved"] == 0.6
    assert billed["mean_seconds_saved"] == 1.0
    assert billed["routing_authorized"] is False


def test_prove_counterfactual_is_a_real_percent(aegis_tmp, tmp_path):
    init_home()
    src = tmp_path / "mod.py"
    src.write_text("def hello(x):\n    return x + 1\n" * 40, encoding="utf-8")
    proof = prove([str(src)])
    assert proof["ok"] is True
    assert proof["savings_percent"] is None
    assert proof["naive_tokens"] > proof["packed_tokens"]
    assert proof["tokens_saved_counterfactual"] == proof["naive_tokens"] - proof["packed_tokens"]
    assert proof["reduction_percent_counterfactual"] == round(
        (proof["tokens_saved_counterfactual"] / float(proof["naive_tokens"])) * 100.0, 1
    )
    assert proof["reduction_percent_counterfactual"] > 0


def test_honesty_and_demo_print_live_numbers(aegis_tmp, tmp_path):
    init_home()
    record(kind="pack", task="demo-yield", mode="explore", raw_in=800, processed_in=200)
    _pair(task_id="yh-demo", baseline_usd=0.02, governed_usd=0.005)

    beat = honesty()
    live = beat["live_yield"]
    assert beat["savings_percent"] is None
    assert beat["routing_authorized"] is False
    assert live["ledger_tokens_saved_local"] == 600
    assert live["billed_pairs"]["total_cost_usd_saved"] == 0.015
    assert live["billed_pairs"]["paired_tasks"] == 1

    sample = tmp_path / "sample.py"
    sample.write_text("x = 1\n", encoding="utf-8")
    payload = run([str(sample)])
    assert payload["yield"]["ledger_tokens_saved_local"] == 600
    assert payload["yield"]["billed_pairs"]["total_cost_usd_saved"] == 0.015
    assert payload["beat4_honesty"]["live_yield"]["ledger_tokens_saved_local"] == 600
    text = format_run(payload)
    assert "ledger_saved=600 tok" in text
    assert "billed_pairs=1" in text
    assert "Δ$0.015" in text
    assert "savings_percent=null" in text


def test_doctor_yield_honest_passes_with_real_numbers(aegis_tmp):
    init_home()
    record(kind="pack", task="doctor-yield", mode="explore", raw_in=500, processed_in=100)
    _pair(task_id="yh-doc", baseline_usd=2.0, governed_usd=0.5)
    report = doctor_report()
    by = {c["name"]: c for c in report["checks"]}
    assert by["yield_honest"]["pass"] is True
    detail = by["yield_honest"]["detail"]
    assert "savings_percent=None" in detail
    assert "ledger_saved=400" in detail
    assert "billed_Δusd=1.5" in detail


def test_yield_report_cli_json(aegis_tmp, capsys):
    init_home()
    record(kind="pack", task="cli-yield", mode="explore", raw_in=300, processed_in=100)
    _pair(task_id="yh-cli", baseline_usd=0.8, governed_usd=0.3)
    assert main(["yield", "report"]) == 0
    payload = json.loads(capsys.readouterr().out)
    result = payload.get("result") or payload
    assert result["savings_percent"] is None
    assert result["ledger_tokens_saved_local"] == 200
    assert result["billed_pairs"]["total_cost_usd_saved"] == 0.5
    assert result["billed_pairs"]["routing_authorized"] is False
