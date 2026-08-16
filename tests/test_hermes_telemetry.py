"""Hermes token-pair telemetry. Never invents savings."""

from aegis.wrappers.hermes_telemetry import (
    comparable_usage,
    extract_token_counts,
    record_pair,
    token_delta,
)


def test_extract_maps_cache_read_alias():
    counts = extract_token_counts(
        {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "cache_read": 4}
    )
    assert counts["cache_read_tokens"] == 4
    assert counts["total_tokens"] == 12


def test_comparable_usage_requires_three_counts():
    assert comparable_usage({"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})
    assert not comparable_usage({"input_tokens": 1, "output_tokens": 2})
    assert not comparable_usage(None)


def test_token_delta_null_unless_pair_valid():
    control = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
    treatment = {"input_tokens": 80, "output_tokens": 8, "total_tokens": 88}
    assert token_delta(control, treatment, pair_valid=False) is None
    delta = token_delta(control, treatment, pair_valid=True)
    assert delta == {"input_tokens": 20, "output_tokens": 2, "total_tokens": 22}


def test_record_pair_appends_and_nulls_savings(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    rec = record_pair(
        task_id="r012-demo",
        control_usage={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
        treatment_usage={"input_tokens": 18, "output_tokens": 4, "total_tokens": 22},
        pair_valid=False,
        model="unspecified",
        provider="none",
    )
    assert rec["savings_percent"] is None
    assert rec["token_delta"] is None
    assert rec["efficiency_result"] == "invalid_pair"
    path = tmp_path / "home" / "hermes_token_pairs.jsonl"
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_record_pair_valid_writes_delta_not_percent(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    rec = record_pair(
        task_id="r012-valid",
        control_usage={"input_tokens": 40, "output_tokens": 6, "total_tokens": 46},
        treatment_usage={"input_tokens": 30, "output_tokens": 6, "total_tokens": 36},
        pair_valid=True,
    )
    assert rec["pair_valid"] is True
    assert rec["token_delta"]["total_tokens"] == 10
    assert rec["savings_percent"] is None
