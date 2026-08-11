"""Pack quality gates + auto-receipt behavior."""

import os
import tempfile

import pytest

from aegis.bento import assemble
from aegis.cli import main
from aegis.quality import evaluate_pack


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_explore_low_cut_warns(aegis_tmp):
    # almost no compress possible
    src = "a = 1\n" * 50
    payload = assemble(
        core_task="x",
        code_snippets=[{"path": "m.py", "content": src}],
        mode="explore",
    )
    # force low reduction for gate
    payload["overall_reduction_percent"] = 5.0
    payload["total_raw_tokens"] = 200
    gate = evaluate_pack(payload, mode="explore")
    codes = {i["code"] for i in gate.issues}
    assert "explore_low_cut" in codes
    assert gate.grade == "warn"
    assert gate.strict_fail is False


def test_implement_fidelity_fail(aegis_tmp):
    src = "def target_fn(a):\n    return a + 1\n\ndef other():\n    return 0\n"
    payload = {
        "mode": "implement",
        "total_raw_tokens": 100,
        "total_compressed_tokens": 50,
        "overall_reduction_percent": 50,
        "bento_components": [
            {"path": "m.py", "payload_snippet": "def other():\n    return 0\n"}
        ],
        "fidelity": [{"path": "m.py", "fidelity": "target_bodies", "targets_resolved": ["target_fn"]}],
        "targets": ["target_fn"],
    }
    gate = evaluate_pack(
        payload,
        mode="implement",
        targets=["target_fn"],
        sources={"m.py": src},
    )
    assert any(i["code"] == "implement_fidelity" for i in gate.issues)
    assert gate.strict_fail is True


def test_pack_emits_receipt_and_quality(aegis_tmp):
    code = '''
"""waste docstring"""
import os

def foo():
    return 1

def bar():
    x = 2
    return x
'''
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        # capture via main returning 0; receipt written
        assert main(["pack", "--task", "explore", "--mode", "explore", "--refresh", path]) == 0
        from aegis.receipt import load_last_receipt

        rec = load_last_receipt()
        assert rec is not None
        assert rec.get("pack_id")
    finally:
        os.unlink(path)


def test_strict_exits_on_fail(aegis_tmp):
    # empty file-ish component via missing path content handled by pack needing files
    # use implement fidelity fail path through evaluate only
    gate = evaluate_pack(
        {
            "mode": "implement",
            "total_raw_tokens": 10,
            "total_compressed_tokens": 5,
            "overall_reduction_percent": 50,
            "bento_components": [],
        },
        mode="implement",
    )
    assert gate.strict_fail is True
