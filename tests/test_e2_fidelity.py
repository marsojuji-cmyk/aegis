"""E2 implement-mode fidelity — never drop target bodies."""

from aegis.ast_slice import build_implement_payload, extract_python_units
from aegis.bento import assert_implement_fidelity, assemble

SAMPLE = '''
"""Module waste."""
import os

class Alpha:
    def method_a(self, x):
        y = x + 1
        z = y * 2
        return z

    def method_b(self):
        return 42

def helper():
    return "no"

def target_fn(a, b):
    # full body must survive implement pack
    total = a + b
    if total > 10:
        return total * 2
    return total - 1
'''


def test_implement_includes_full_target_body():
    payload, meta = build_implement_payload(SAMPLE, targets=["target_fn"])
    assert meta["fidelity"] == "target_bodies"
    assert "target_fn" in meta["targets_resolved"] or any(
        "target_fn" in t for t in meta["targets_resolved"]
    )
    assert "total = a + b" in payload
    assert "return total - 1" in payload
    assert "def helper" in payload  # neighbor signature area
    # helper body should NOT be fully required — only sig
    assert assert_implement_fidelity(SAMPLE, payload, ["target_fn"])


def test_implement_no_targets_keeps_full_file():
    payload, meta = build_implement_payload(SAMPLE, targets=None, task="edit the module")
    assert meta["fidelity"] == "full_file"
    assert "def target_fn" in payload
    assert "total = a + b" in payload


def test_explore_drops_bodies():
    from aegis.ast_slice import build_explore_payload

    exp = build_explore_payload(SAMPLE)
    assert "def target_fn" in exp or "target_fn" in exp
    assert "total = a + b" not in exp


def test_assemble_implement_mode():
    result = assemble(
        core_task="fix target_fn",
        code_snippets=[{"path": "s.py", "content": SAMPLE}],
        mode="implement",
        targets=["target_fn"],
    )
    assert result["engine"] in ("product_e2", "product_e3")
    text = result["bento_components"][0]["payload_snippet"]
    assert "total = a + b" in text
    assert assert_implement_fidelity(SAMPLE, text, ["target_fn"])


def test_nested_class_method_target():
    payload, meta = build_implement_payload(SAMPLE, targets=["Alpha.method_a"])
    assert "y = x + 1" in payload
    assert "z = y * 2" in payload
