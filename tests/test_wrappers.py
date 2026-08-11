"""OpenAI + Anti-Gravity wrappers through full Aegis pipeline."""

import pytest

from aegis.cli import main
from aegis.providers import detect_provider, list_providers
from aegis.wrappers import AntiGravityWrapper, OpenAIWrapper
from aegis.wrappers.base import intercept_and_route, validate_messages


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_validate_messages():
    assert validate_messages([]) 
    assert not validate_messages([{"role": "user", "content": "hi"}])


def test_detect_antigravity():
    assert detect_provider("gemini-2.0-flash").kind == "antigravity"
    assert detect_provider("", "antigravity").name == "antigravity"
    names = {p["name"] for p in list_providers()}
    assert "openai" in names
    assert "antigravity" in names


def test_openai_wrapper_dry(aegis_tmp, tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    return 1\n")
    client = OpenAIWrapper(dry_run=True)
    resp = client.complete(
        "fix foo",
        task="wrap openai",
        paths=[str(f)],
        mode="explore",
        dry_run=True,
    )
    assert resp["choices"][0]["message"]["content"]
    assert resp["aegis"]["provider"] in ("openai", "mock")
    assert resp["aegis"]["output_id"]
    assert "pipeline" in resp["aegis"]


def test_openai_post_hoc(aegis_tmp):
    resp = OpenAIWrapper.intercept_output(
        "Sure, happy to help!\n\nFixed the bug.\n",
        profile="brief",
        task="posthoc",
    )
    body = resp["choices"][0]["message"]["content"]
    assert "Sure" not in body
    assert resp["aegis"]["output_id"]


def test_antigravity_wrapper_dry(aegis_tmp, tmp_path):
    f = tmp_path / "b.py"
    f.write_text("def bar():\n    return 2\n")
    ag = AntiGravityWrapper(dry_run=True)
    resp = ag.chat(
        "explain bar",
        paths=[str(f)],
        task="ag wrap",
        dry_run=True,
    )
    assert resp["choices"][0]["message"]["content"]
    assert resp["aegis"]["wrapper"] == "antigravity"
    assert resp["aegis"]["output_id"]


def test_antigravity_post_hoc(aegis_tmp):
    resp = AntiGravityWrapper.intercept_output(
        "Here is the answer.\n\nAll good.\n",
        profile="brief",
    )
    assert resp["aegis"]["provider"] == "antigravity"
    assert resp["aegis"]["output_id"]


def test_cli_wrap_openai(aegis_tmp, tmp_path):
    f = tmp_path / "c.py"
    f.write_text("x = 1\n")
    assert (
        main(
            [
                "wrap",
                "--provider",
                "openai",
                "--task",
                "cli wrap",
                "--prompt",
                "hi",
                "--dry-run",
                str(f),
            ]
        )
        == 0
    )


def test_cli_wrap_antigravity(aegis_tmp):
    assert (
        main(
            [
                "wrap",
                "--provider",
                "antigravity",
                "--task",
                "cli ag",
                "--prompt",
                "hello",
                "--dry-run",
            ]
        )
        == 0
    )


def test_intercept_validation_fails(aegis_tmp):
    resp = intercept_and_route(
        provider="openai",
        model="mock",
        messages=[],
        dry_run=True,
    )
    assert resp.get("ok") is False
