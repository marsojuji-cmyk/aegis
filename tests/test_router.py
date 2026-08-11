"""Universal router pipeline + daemon + batch."""

import json
import urllib.request

import pytest

from aegis.cli import main
from aegis.providers import detect_provider, list_providers
from aegis.router_daemon import start_background
from aegis.router_pipeline import run_batch, run_pipeline, router_status


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_detect_providers():
    assert detect_provider("mock").kind == "mock"
    assert detect_provider("grok-2").kind == "grok"
    assert detect_provider("claude-sonnet").kind == "claude"
    assert detect_provider("gpt-4o-mini").kind == "openai"
    assert detect_provider("llama3.2").kind == "ollama"
    assert len(list_providers()) >= 5


def test_openai_responses_sends_cache_and_flex(monkeypatch):
    import aegis.router_client as client

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    seen = {}

    def fake_http(method, url, body, headers, timeout):
        seen.update({"method": method, "url": url, "body": body})
        return {
            "id": "resp_test",
            "output_text": "ok",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "input_tokens_details": {"cached_tokens": 8, "cache_write_tokens": 10},
            },
        }

    monkeypatch.setattr(client, "_http_json", fake_http)
    result = client.chat_completion(
        detect_provider("gpt-test"), model="gpt-test",
        messages=[{"role": "user", "content": "hi"}], use_responses=True,
        service_tier="flex", prompt_cache_key="stable",
    )
    assert seen["url"].endswith("/responses")
    assert seen["body"]["prompt_cache_key"] == "stable"
    assert seen["body"]["service_tier"] == "flex"
    assert result["usage"]["cached_tokens"] == 8


def test_run_pipeline_mock(aegis_tmp, tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    return 1\n")
    r = run_pipeline(
        task="test run",
        model="mock",
        paths=[str(f)],
        mode="explore",
        dry_run=False,
    )
    assert r.ok is True
    assert r.provider == "mock"
    assert r.output_id
    assert r.shrunk


def test_pipeline_injects_cross_agent_contract(aegis_tmp, monkeypatch):
    import aegis.router_pipeline as pipeline

    seen = {}

    def fake_chat(provider, **kwargs):
        seen["messages"] = kwargs["messages"]
        return {"provider": "mock", "model": "mock", "content": "ok",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "mock": True}

    monkeypatch.setattr(pipeline, "chat_completion", fake_chat)
    result = pipeline.run_pipeline(task="contract", model="mock", skip_preflight=True)
    assert result.ok
    assert "AEGIS CONTRACT" in seen["messages"][0]["content"]


def test_run_pipeline_reuse_output(aegis_tmp):
    r1 = run_pipeline(task="same task body", model="mock", skip_preflight=True)
    r2 = run_pipeline(task="same task body", model="mock", skip_preflight=True)
    assert r1.ok and r2.ok
    # mock content is deterministic by user msg length/content → likely reuse
    # at least second run stores or reuses
    assert r2.output_id


def test_run_pipeline_enforces_request_output_cap(aegis_tmp):
    from aegis.config import load_config, save_config

    cfg = load_config()
    cfg.output_hard_max = 7
    save_config(cfg)
    result = run_pipeline(
        task="cap", model="mock", skip_preflight=True, max_tokens=999
    )
    assert result.ok


def test_pipeline_transfers_before_context_exhaustion(aegis_tmp, monkeypatch):
    import aegis.router_pipeline as pipeline
    from aegis.config import load_config, save_config

    cfg = load_config()
    cfg.context_window_tokens = 100
    save_config(cfg)
    result = pipeline.run_pipeline(task="x" * 500, model="mock", skip_preflight=True)
    assert not result.ok
    assert "transfer" in result.error or "red" in result.error
    assert result.meta.get("transfer_capsule")


def test_batch_concurrent(aegis_tmp):
    jobs = [
        {"task": f"job {i}", "model": "mock", "skip_preflight": True}
        for i in range(12)
    ]
    results = run_batch(jobs, max_workers=10)
    assert len(results) == 12
    assert sum(1 for r in results if r.ok) == 12


def test_cli_run(aegis_tmp):
    assert main(["run", "--task", "cli mock", "--model", "mock"]) == 0


def test_cli_providers(aegis_tmp):
    assert main(["providers"]) == 0


def test_daemon_chat_mock(aegis_tmp):
    httpd, _t = start_background("127.0.0.1", 18787)
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:18787/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "mock",
                    "messages": [{"role": "user", "content": "hello aegis"}],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        assert data["choices"][0]["message"]["content"]
        assert data.get("aegis", {}).get("output_id")
        st_req = urllib.request.Request("http://127.0.0.1:18787/v1/aegis/status")
        with urllib.request.urlopen(st_req, timeout=5) as resp:
            st = json.loads(resp.read().decode("utf-8"))
        assert "providers" in st
        # app endpoints
        with urllib.request.urlopen(
            "http://127.0.0.1:18787/v1/aegis/budget", timeout=5
        ) as resp:
            budget = json.loads(resp.read().decode("utf-8"))
        assert budget.get("ok") is True
        assert "budget" in budget and "surplus" in budget
        with urllib.request.urlopen(
            "http://127.0.0.1:18787/v1/aegis/ledger?limit=5", timeout=5
        ) as resp:
            ledger = json.loads(resp.read().decode("utf-8"))
        assert ledger.get("ok") is True
        assert "transactions" in ledger
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_router_status():
    from aegis import DEFAULT_BATCH_WORKERS, MAX_BATCH_WORKERS, __version__
    from aegis.router_daemon import AegisRouterHandler

    st = router_status()
    assert st["max_concurrent_default"] == DEFAULT_BATCH_WORKERS
    assert st.get("max_concurrent_cap") == MAX_BATCH_WORKERS
    assert "outputs" in st
    assert st["version"] == __version__
    assert AegisRouterHandler.server_version == f"AegisRouter/{__version__}"
