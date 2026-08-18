"""Billed receipt collector. Does not authorize routing."""

import hashlib
import json

from aegis.cost_provenance import provider_window_status
from aegis.outcomes import outcome_report
from aegis.receipt_collect import (
    PAIR_WORKFLOW,
    collect_matched_pairs,
    collect_receipts,
    extract_billed_usd,
    load_api_key,
    probe,
)


def test_extract_billed_usd_from_usage_cost():
    assert extract_billed_usd({"usage": {"cost": 0.00012, "prompt_tokens": 9}}) == 0.00012


def test_extract_billed_usd_refuses_token_only_bodies():
    assert extract_billed_usd({"usage": {"prompt_tokens": 9, "completion_tokens": 1}}) is None


def test_probe_missing_key(monkeypatch):
    monkeypatch.delenv("NOUS_API_KEY", raising=False)
    monkeypatch.delenv("AGIS_API_KEY", raising=False)
    out = probe({})
    assert out["ok"] is False
    assert out["ready_to_execute"] is False
    assert out["blocked"] == "missing_key"
    assert out["routing_authorized"] is False
    assert out["rows_written"] == 0


def test_probe_refuses_denylisted_key():
    secret = "sk-test-burned"
    digest = hashlib.sha256(secret.encode()).hexdigest()
    out = load_api_key({"NOUS_API_KEY": secret}, burned=frozenset({digest}))
    assert out["ok"] is False
    assert out["blocked"] == "burned_key"
    assert out["key"] == ""


def test_execute_writes_observed_rows_and_does_not_authorize(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NOUS_API_KEY", "sk-nous-test-rotated")

    def fake_post(url, headers, body):
        assert "Bearer sk-nous-test-rotated" in headers["Authorization"]
        assert body["model"] == "deepseek/deepseek-v4-pro"
        return {
            "id": "chatcmpl-test",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1, "cost": 0.00004},
        }

    out = collect_receipts(execute=True, count=5, post_json=fake_post)
    assert out["ok"] is True
    assert out["rows_written"] == 5
    assert out["routing_authorized"] is False
    assert out["provider_window_ready"] is True
    assert provider_window_status(limit=5)["provider_window_ready"] is True
    assert outcome_report()["routing_authorized"] is False
    assert all(row["cost_source"] == "nous_api" for row in out["rows"])


def test_execute_does_not_mint_when_bill_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NOUS_API_KEY", "sk-nous-test-rotated")

    def fake_post(url, headers, body):
        return {"usage": {"prompt_tokens": 8, "completion_tokens": 1}}

    out = collect_receipts(execute=True, count=5, post_json=fake_post)
    assert out["ok"] is False
    assert out["rows_written"] == 0
    assert out["routing_authorized"] is False
    assert "billed USD missing" in out["errors"][0]


def test_collect_receipts_cli_probe_never_authorizes(monkeypatch, capsys):
    monkeypatch.delenv("NOUS_API_KEY", raising=False)
    monkeypatch.delenv("AGIS_API_KEY", raising=False)
    from aegis.cli import main

    assert main(["outcome", "collect-receipts"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["routing_authorized"] is False
    assert payload["mode"] == "probe"
    assert payload["blocked"] == "missing_key"


def test_matched_pairs_do_not_authorize_without_cost_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NOUS_API_KEY", "sk-nous-test-rotated")

    def fake_post(url, headers, body):
        return {
            "id": "chatcmpl-pair",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1, "cost": 0.00004},
        }

    out = collect_matched_pairs(execute=True, pairs=10, post_json=fake_post)
    assert out["ok"] is True
    assert out["rows_written"] == 20
    assert out["paired_tasks"] == 10
    assert out["routing_authorized"] is False
    assert out["outcome_routing_authorized"] is False
    report = outcome_report(workflow=PAIR_WORKFLOW)
    assert report["paired_tasks"] == 10
    assert report["cost_comparison_complete"] is True
    assert report["routing_authorized"] is False
    assert provider_window_status(limit=5)["provider_window_ready"] is True


def test_cheaper_governed_can_pass_pair_math_without_cli_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NOUS_API_KEY", "sk-nous-test-rotated")

    def fake_post(url, headers, body):
        cost = 0.00004 if body["model"].endswith("pro") else 0.00001
        return {
            "id": "chatcmpl-delta",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1, "cost": cost},
        }

    out = collect_matched_pairs(
        execute=True, pairs=10, model="deepseek/deepseek-v4-pro",
        governed_model="openai/gpt-5.4-nano", post_json=fake_post,
    )
    assert out["ok"] is True
    assert out["routing_authorized"] is False
    report = outcome_report(workflow=PAIR_WORKFLOW)
    assert report["paired_tasks"] == 10
    assert report["total_cost_usd_saved"] > 0
    assert report["routing_authorized"] is True
    assert report["decision"] == "eligible for routing trial"
